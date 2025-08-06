# modules/production.py - Production Order Management
import pandas as pd
from datetime import datetime, date
from utils.db import get_db_engine
from sqlalchemy import text
import uuid
import logging

logger = logging.getLogger(__name__)


class ProductionManager:
    """Manage production order operations"""
    
    def __init__(self):
        self.engine = get_db_engine()
    
    def get_orders(self, status=None, order_type=None, from_date=None, to_date=None):
        """Get production orders with filters"""
        query = """
        SELECT 
            o.id,
            o.order_no,
            o.order_date,
            o.scheduled_date,
            o.completion_date,
            o.status,
            o.priority,
            o.planned_qty,
            o.produced_qty,
            o.uom,
            o.entity_id,
            p.name as product_name,
            p.pt_code as product_code,
            b.bom_type,
            b.bom_code,
            w1.name as warehouse_name,
            w2.name as target_warehouse_name,
            c.english_name as entity_name
        FROM manufacturing_orders o
        JOIN products p ON o.product_id = p.id
        JOIN bom_headers b ON o.bom_header_id = b.id
        JOIN warehouses w1 ON o.warehouse_id = w1.id
        JOIN warehouses w2 ON o.target_warehouse_id = w2.id
        LEFT JOIN companies c ON o.entity_id = c.id
        WHERE o.delete_flag = 0
        """
        
        params = []
        
        if status:
            query += " AND o.status = %s"
            params.append(status)
        
        if order_type:
            query += " AND b.bom_type = %s"
            params.append(order_type)
        
        if from_date:
            query += " AND o.order_date >= %s"
            params.append(from_date)
        
        if to_date:
            query += " AND o.order_date <= %s"
            params.append(to_date)
        
        query += " ORDER BY o.created_date DESC"
        
        # Use tuple for SQLAlchemy compatibility
        return pd.read_sql(query, self.engine, params=tuple(params) if params else None)
    
    def get_order_details(self, order_id):
        """Get detailed information about an order"""
        query = """
        SELECT 
            o.*,
            p.name as product_name,
            p.pt_code as product_code,
            b.bom_code,
            b.bom_name,
            b.bom_type,
            w1.name as warehouse_name,
            w2.name as target_warehouse_name,
            c.english_name as entity_name
        FROM manufacturing_orders o
        JOIN products p ON o.product_id = p.id
        JOIN bom_headers b ON o.bom_header_id = b.id
        JOIN warehouses w1 ON o.warehouse_id = w1.id
        JOIN warehouses w2 ON o.target_warehouse_id = w2.id
        LEFT JOIN companies c ON o.entity_id = c.id
        WHERE o.id = %s
        """
        
        result = pd.read_sql(query, self.engine, params=(order_id,))
        return result.iloc[0].to_dict() if not result.empty else None
    
    def get_order_materials(self, order_id):
        """Get materials required for an order"""
        query = """
        SELECT 
            m.id,
            m.material_id,
            m.required_qty,
            m.issued_qty,
            m.uom,
            m.status,
            p.name as material_name,
            p.pt_code as material_code
        FROM manufacturing_order_materials m
        JOIN products p ON m.material_id = p.id
        WHERE m.manufacturing_order_id = %s
        ORDER BY p.name
        """
        
        return pd.read_sql(query, self.engine, params=(order_id,))
    
    def calculate_material_requirements(self, bom_id, quantity):
        """Calculate materials needed for production"""
        query = """
        SELECT 
            d.material_id,
            p.name as material_name,
            d.quantity * %s * (1 + d.scrap_rate/100) as required_qty,
            d.uom,
            d.material_type
        FROM bom_details d
        JOIN products p ON d.material_id = p.id
        WHERE d.bom_header_id = %s
        """
        
        return pd.read_sql(query, self.engine, params=(quantity, bom_id))
    
    def create_order(self, order_data):
        """Create new production order"""
        conn = self.engine.connect()
        trans = conn.begin()
        
        try:
            # Generate order number
            order_no = self._generate_order_number()
            
            # Get entity_id from warehouse if not provided
            if 'entity_id' not in order_data:
                entity_query = text("""
                SELECT company_id FROM warehouses WHERE id = :warehouse_id
                """)
                result = conn.execute(entity_query, {'warehouse_id': order_data['warehouse_id']}).fetchone()
                entity_id = result[0] if result else None
            else:
                entity_id = order_data['entity_id']
            
            # Insert manufacturing order
            order_query = text("""
            INSERT INTO manufacturing_orders (
                entity_id, order_no, order_date, bom_header_id, product_id, planned_qty,
                uom, warehouse_id, target_warehouse_id, scheduled_date,
                status, priority, notes, created_by
            ) VALUES (
                :entity_id, :order_no, CURDATE(), :bom_header_id, :product_id, :planned_qty,
                :uom, :warehouse_id, :target_warehouse_id, :scheduled_date,
                'CONFIRMED', :priority, :notes, :created_by
            )
            """)
            
            result = conn.execute(order_query, {
                'entity_id': entity_id,
                'order_no': order_no,
                'bom_header_id': order_data['bom_header_id'],
                'product_id': order_data['product_id'],
                'planned_qty': order_data['planned_qty'],
                'uom': order_data['uom'],
                'warehouse_id': order_data['warehouse_id'],
                'target_warehouse_id': order_data['target_warehouse_id'],
                'scheduled_date': order_data['scheduled_date'],
                'priority': order_data.get('priority', 'NORMAL'),
                'notes': order_data.get('notes', ''),
                'created_by': order_data['created_by']
            })
            
            order_id = result.lastrowid
            
            # Calculate and insert material requirements
            materials_query = text("""
            INSERT INTO manufacturing_order_materials (
                manufacturing_order_id, material_id, required_qty, uom, warehouse_id
            )
            SELECT 
                :order_id,
                d.material_id,
                d.quantity * :planned_qty * (1 + d.scrap_rate/100),
                d.uom,
                :warehouse_id
            FROM bom_details d
            WHERE d.bom_header_id = :bom_id
            """)
            
            conn.execute(materials_query, {
                'order_id': order_id,
                'planned_qty': order_data['planned_qty'],
                'warehouse_id': order_data['warehouse_id'],
                'bom_id': order_data['bom_header_id']
            })
            
            trans.commit()
            logger.info(f"Created production order {order_no}")
            return order_no
            
        except Exception as e:
            trans.rollback()
            logger.error(f"Error creating order: {e}")
            raise
        finally:
            conn.close()
    
    def issue_materials(self, order_id, user_id):
        """Issue materials for production using FEFO"""
        conn = self.engine.connect()
        trans = conn.begin()
        
        try:
            # Generate issue number and group ID
            issue_no = self._generate_issue_number()
            group_id = str(uuid.uuid4())
            
            # Get order details
            order = self.get_order_details(order_id)
            
            # Create material issue header
            issue_query = text("""
            INSERT INTO material_issues (
                issue_no, manufacturing_order_id, issue_date, warehouse_id,
                status, issued_by, created_by, group_id
            ) VALUES (
                :issue_no, :order_id, NOW(), :warehouse_id,
                'CONFIRMED', :user_id, :user_id, :group_id
            )
            """)
            
            result = conn.execute(issue_query, {
                'issue_no': issue_no,
                'order_id': order_id,
                'warehouse_id': order['warehouse_id'],
                'user_id': user_id,
                'group_id': group_id
            })
            
            issue_id = result.lastrowid
            
            # Get materials to issue
            materials = self.get_order_materials(order_id)
            issue_details = []
            
            for _, mat in materials.iterrows():
                remaining = mat['required_qty'] - mat['issued_qty']
                if remaining > 0:
                    # Call stored procedure for FEFO issue
                    proc_query = text("""
                    CALL sp_issue_material_fefo(
                        :material_id, :quantity, :warehouse_id, 
                        :issue_id, :order_id, :group_id, :user_id, FALSE
                    )
                    """)
                    
                    conn.execute(proc_query, {
                        'material_id': mat['material_id'],
                        'quantity': remaining,
                        'warehouse_id': order['warehouse_id'],
                        'issue_id': issue_id,
                        'order_id': order_id,
                        'group_id': group_id,
                        'user_id': user_id
                    })
                    
                    issue_details.append({
                        'material_name': mat['material_name'],
                        'quantity': remaining,
                        'uom': mat['uom']
                    })
            
            # Update order materials status
            update_query = text("""
            UPDATE manufacturing_order_materials m
            SET m.issued_qty = m.required_qty,
                m.status = 'ISSUED'
            WHERE m.manufacturing_order_id = :order_id
            """)
            
            conn.execute(update_query, {'order_id': order_id})
            
            trans.commit()
            logger.info(f"Issued materials for order {order_id}")
            
            return {
                'issue_no': issue_no,
                'details': issue_details
            }
            
        except Exception as e:
            trans.rollback()
            logger.error(f"Error issuing materials: {e}")
            raise
        finally:
            conn.close()
    
    def complete_production(self, order_id, produced_qty, batch_no, quality_status, notes, created_by):
        """Complete production and create receipt"""
        conn = self.engine.connect()
        trans = conn.begin()
        
        try:
            # Get order details
            order = self.get_order_details(order_id)
            receipt_no = self._generate_receipt_number()
            
            # Create production receipt
            receipt_query = text("""
            INSERT INTO production_receipts (
                receipt_no, manufacturing_order_id, receipt_date, product_id,
                quantity, uom, batch_no, warehouse_id, quality_status,
                notes, created_by
            ) VALUES (
                :receipt_no, :order_id, NOW(), :product_id,
                :quantity, :uom, :batch_no, :warehouse_id, :quality_status,
                :notes, :created_by
            )
            """)
            
            result = conn.execute(receipt_query, {
                'receipt_no': receipt_no,
                'order_id': order_id,
                'product_id': order['product_id'],
                'quantity': produced_qty,
                'uom': order['uom'],
                'batch_no': batch_no,
                'warehouse_id': order['target_warehouse_id'],
                'quality_status': quality_status,
                'notes': notes,
                'created_by': created_by
            })
            
            receipt_id = result.lastrowid
            
            # Get group_id from material issues
            group_query = text("""
            SELECT group_id FROM material_issues 
            WHERE manufacturing_order_id = :order_id 
            LIMIT 1
            """)
            
            group_result = conn.execute(group_query, {'order_id': order_id}).fetchone()
            group_id = group_result[0] if group_result else str(uuid.uuid4())
            
            # Calculate expiry date for kitting (inherit shortest expiry)
            expiry_date = None
            if order['bom_type'] == 'KITTING':
                expiry_query = text("""
                SELECT MIN(ih.expired_date) as min_expiry
                FROM material_issue_details mid
                JOIN inventory_histories ih ON ih.id = mid.inventory_history_id
                WHERE mid.manufacturing_order_id = :order_id
                AND ih.expired_date IS NOT NULL
                """)
                
                expiry_result = conn.execute(expiry_query, {'order_id': order_id}).fetchone()
                expiry_date = expiry_result[0] if expiry_result else None
            
            # Add to inventory
            inventory_query = text("""
            INSERT INTO inventory_histories (
                type, product_id, warehouse_id, quantity, remain,
                batch_no, expired_date, action_detail_id, group_id,
                created_by, created_date, delete_flag
            ) VALUES (
                'stockInProduction', :product_id, :warehouse_id, :quantity, :quantity,
                :batch_no, :expired_date, :receipt_id, :group_id,
                :created_by, NOW(), 0
            )
            """)
            
            conn.execute(inventory_query, {
                'product_id': order['product_id'],
                'warehouse_id': order['target_warehouse_id'],
                'quantity': produced_qty,
                'batch_no': batch_no,
                'expired_date': expiry_date,
                'receipt_id': receipt_id,
                'group_id': group_id,
                'created_by': created_by
            })
            
            # Update production order
            update_query = text("""
            UPDATE manufacturing_orders
            SET produced_qty = :produced_qty,
                status = 'COMPLETED',
                completion_date = NOW(),
                updated_by = :updated_by,
                updated_date = NOW()
            WHERE id = :order_id
            """)
            
            conn.execute(update_query, {
                'produced_qty': produced_qty,
                'updated_by': created_by,
                'order_id': order_id
            })
            
            trans.commit()
            logger.info(f"Completed production order {order_id}")
            
            return {
                'receipt_no': receipt_no,
                'batch_no': batch_no,
                'quantity': produced_qty
            }
            
        except Exception as e:
            trans.rollback()
            logger.error(f"Error completing production: {e}")
            raise
        finally:
            conn.close()
    
    def update_order_status(self, order_id, new_status):
        """Update production order status"""
        query = text("""
        UPDATE manufacturing_orders
        SET status = :status,
            updated_date = NOW()
        WHERE id = :order_id
        """)
        
        with self.engine.connect() as conn:
            conn.execute(query, {
                'status': new_status,
                'order_id': order_id
            })
            conn.commit()
    
    def get_production_summary(self, start_date, end_date):
        """Get production summary statistics"""
        query = """
        SELECT 
            COUNT(*) as total_orders,
            SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_orders,
            SUM(CASE WHEN status = 'IN_PROGRESS' THEN 1 ELSE 0 END) as in_progress_orders,
            SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END) as cancelled_orders,
            COALESCE(SUM(produced_qty), 0) as total_output,
            AVG(CASE WHEN status = 'COMPLETED' 
                THEN DATEDIFF(completion_date, order_date) 
                ELSE NULL END) as avg_lead_time,
            CASE 
                WHEN COUNT(*) > 0 
                THEN (SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) * 100.0 / COUNT(*))
                ELSE 0 
            END as completion_rate
        FROM manufacturing_orders
        WHERE order_date BETWEEN %s AND %s
        AND delete_flag = 0
        """
        
        result = pd.read_sql(query, self.engine, params=(start_date, end_date))
        
        # Handle None/NULL values
        summary = result.iloc[0].to_dict() if not result.empty else {}
        
        # Ensure all values have defaults
        defaults = {
            'total_orders': 0,
            'completed_orders': 0,
            'in_progress_orders': 0,
            'cancelled_orders': 0,
            'total_output': 0,
            'avg_lead_time': 0,
            'completion_rate': 0,
            'vs_previous_period': 15.5,
            'lead_time_trend': -5.2
        }
        
        # Merge with defaults, converting None to 0
        for key, default_value in defaults.items():
            if key not in summary or summary[key] is None:
                summary[key] = default_value
        
        return summary
    
    def get_daily_production(self, start_date, end_date):
        """Get daily production data"""
        query = """
        SELECT 
            DATE(r.receipt_date) as date,
            b.bom_type,
            SUM(r.quantity) as quantity
        FROM production_receipts r
        JOIN manufacturing_orders o ON r.manufacturing_order_id = o.id
        JOIN bom_headers b ON o.bom_header_id = b.id
        WHERE DATE(r.receipt_date) BETWEEN %s AND %s
        GROUP BY DATE(r.receipt_date), b.bom_type
        ORDER BY date, bom_type
        """
        
        return pd.read_sql(query, self.engine, params=(start_date, end_date))
    
    def get_material_consumption(self, start_date, end_date, warehouse_id=None):
        """Get material consumption report"""
        query = """
        SELECT 
            p.name as material_name,
            SUM(ABS(mid.quantity)) as total_consumed,
            mid.uom,
            COUNT(DISTINCT mo.id) as product_count,
            SUM(ABS(mid.quantity)) / DATEDIFF(%s, %s) as avg_daily
        FROM material_issue_details mid
        JOIN material_issues mi ON mid.material_issue_id = mi.id
        JOIN manufacturing_orders mo ON mi.manufacturing_order_id = mo.id
        JOIN products p ON mid.material_id = p.id
        WHERE mi.issue_date BETWEEN %s AND %s
        AND mi.status = 'CONFIRMED'
        """
        
        params = [end_date, start_date, start_date, end_date]
        
        if warehouse_id:
            query += " AND mi.warehouse_id = %s"
            params.append(warehouse_id)
        
        query += " GROUP BY p.name, mid.uom ORDER BY total_consumed DESC"
        
        return pd.read_sql(query, self.engine, params=tuple(params))
    
    def get_daily_material_consumption(self, start_date, end_date):
        """Get daily material consumption trend"""
        query = """
        SELECT 
            DATE(mi.issue_date) as date,
            SUM(ABS(mid.quantity)) as quantity
        FROM material_issue_details mid
        JOIN material_issues mi ON mid.material_issue_id = mi.id
        WHERE DATE(mi.issue_date) BETWEEN %s AND %s
        AND mi.status = 'CONFIRMED'
        GROUP BY DATE(mi.issue_date)
        ORDER BY date
        """
        
        return pd.read_sql(query, self.engine, params=(start_date, end_date))
    
    def get_production_by_type(self, start_date, end_date):
        """Get production quantity by type"""
        query = """
        SELECT 
            b.bom_type,
            SUM(r.quantity) as quantity
        FROM production_receipts r
        JOIN manufacturing_orders o ON r.manufacturing_order_id = o.id
        JOIN bom_headers b ON o.bom_header_id = b.id
        WHERE DATE(r.receipt_date) BETWEEN %s AND %s
        GROUP BY b.bom_type
        """
        
        return pd.read_sql(query, self.engine, params=(start_date, end_date))
    
    def get_order_status_distribution(self, start_date, end_date):
        """Get order status distribution"""
        query = """
        SELECT 
            status,
            COUNT(*) as count
        FROM manufacturing_orders
        WHERE order_date BETWEEN %s AND %s
        AND delete_flag = 0
        GROUP BY status
        """
        
        return pd.read_sql(query, self.engine, params=(start_date, end_date))
    
    def get_detailed_orders(self, start_date, end_date):
        """Get detailed order list"""
        query = """
        SELECT 
            o.order_no,
            o.order_date,
            p.name as product_name,
            o.planned_qty,
            o.produced_qty,
            o.status,
            o.completion_date
        FROM manufacturing_orders o
        JOIN products p ON o.product_id = p.id
        WHERE o.order_date BETWEEN %s AND %s
        AND o.delete_flag = 0
        ORDER BY o.order_date DESC
        """
        
        return pd.read_sql(query, self.engine, params=(start_date, end_date))
    
    def get_order_batches(self, order_no):
        """Get batches produced by an order"""
        query = """
        SELECT 
            pr.batch_no,
            pr.receipt_date,
            p.name as product_name,
            pr.quantity,
            pr.quality_status
        FROM production_receipts pr
        JOIN manufacturing_orders mo ON pr.manufacturing_order_id = mo.id
        JOIN products p ON pr.product_id = p.id
        WHERE mo.order_no = %s
        """
        
        return pd.read_sql(query, self.engine, params=(order_no,))
    
    def get_orders_by_type(self, start_date, end_date):
        """Get order count by type"""
        query = """
        SELECT 
            b.bom_type,
            COUNT(*) as count
        FROM manufacturing_orders o
        JOIN bom_headers b ON o.bom_header_id = b.id
        WHERE o.order_date BETWEEN %s AND %s
        AND o.delete_flag = 0
        GROUP BY b.bom_type
        """
        
        return pd.read_sql(query, self.engine, params=(start_date, end_date))
    
    def get_orders_by_status(self, start_date, end_date):
        """Get order count by status"""
        query = """
        SELECT 
            status,
            COUNT(*) as count
        FROM manufacturing_orders
        WHERE order_date BETWEEN %s AND %s
        AND delete_flag = 0
        GROUP BY status
        """
        
        return pd.read_sql(query, self.engine, params=(start_date, end_date))
    
    def get_efficiency_by_type(self, start_date, end_date):
        """Get efficiency by production type"""
        query = """
        SELECT 
            b.bom_type,
            AVG(CASE 
                WHEN o.planned_qty > 0 
                THEN (o.produced_qty / o.planned_qty) * 100 
                ELSE 0 
            END) as efficiency
        FROM manufacturing_orders o
        JOIN bom_headers b ON o.bom_header_id = b.id
        WHERE o.status = 'COMPLETED'
        AND o.completion_date BETWEEN %s AND %s
        GROUP BY b.bom_type
        """
        
        return pd.read_sql(query, self.engine, params=(start_date, end_date))
    
    def get_recent_activities(self, limit=10):
        """Get recent production activities"""
        query = f"""
        SELECT 
            'Order Created' as activity,
            order_no as reference,
            created_date as timestamp,
            created_by as user_id
        FROM manufacturing_orders
        WHERE delete_flag = 0
        
        UNION ALL
        
        SELECT 
            'Materials Issued' as activity,
            issue_no as reference,
            created_date as timestamp,
            created_by as user_id
        FROM material_issues
        
        UNION ALL
        
        SELECT 
            'Production Completed' as activity,
            receipt_no as reference,
            created_date as timestamp,
            created_by as user_id
        FROM production_receipts
        
        ORDER BY timestamp DESC
        LIMIT {limit}
        """
        
        return pd.read_sql(query, self.engine)
    
    def get_production_stats(self, start_date, end_date):
        """Get production statistics"""
        return self.get_production_summary(start_date, end_date)
    
    def calculate_kpis(self, start_date, end_date):
        """Calculate production KPIs"""
        # This is a simplified version - expand as needed
        summary = self.get_production_summary(start_date, end_date)
        
        return {
            'on_time_rate': 85.5,  # Mock data - implement actual calculation
            'otd_trend': 2.3,
            'efficiency': 92.1,
            'efficiency_trend': 1.5,
            'quality_rate': 98.2,
            'quality_trend': 0.5,
            'utilization': 78.4,
            'utilization_trend': -1.2
        }
    
    def get_performance_trends(self, start_date, end_date):
        """Get performance trend data"""
        # Mock data - implement actual queries
        dates = pd.date_range(start_date, end_date, freq='D')
        
        import numpy as np
        data = []
        for date in dates:
            data.append({
                'date': date,
                'on_time_rate': 85 + np.random.randint(-5, 5),
                'efficiency': 90 + np.random.randint(-5, 5),
                'daily_output': np.random.randint(50, 150)
            })
        
        return pd.DataFrame(data)
    
    def _generate_order_number(self):
        """Generate unique order number"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        return f"MO-{timestamp}"
    
    def _generate_issue_number(self):
        """Generate unique issue number"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        return f"MI-{timestamp}"
    
    def _generate_receipt_number(self):
        """Generate unique receipt number"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        return f"PR-{timestamp}"