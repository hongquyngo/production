# modules/inventory.py - Inventory Management Integration
import pandas as pd
from datetime import datetime, date, timedelta
from utils.db import get_db_engine
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


class InventoryManager:
    """Manage inventory operations for manufacturing"""
    
    def __init__(self):
        self.engine = get_db_engine()
    
    def get_stock_balance(self, product_id, warehouse_id=None):
        """Get current stock balance for a product"""
        query = """
        SELECT 
            COALESCE(SUM(remain), 0) as stock_balance
        FROM inventory_histories
        WHERE product_id = %s
        AND remain > 0
        AND delete_flag = 0
        """
        
        params = [product_id]
        
        if warehouse_id:
            query += " AND warehouse_id = %s"
            params.append(warehouse_id)
        
        result = pd.read_sql(query, self.engine, params=tuple(params))
        return float(result['stock_balance'].iloc[0]) if not result.empty else 0.0
    
    def get_stock_by_batch(self, product_id, warehouse_id):
        """Get stock details by batch with FEFO order"""
        query = """
        SELECT 
            batch_no,
            SUM(remain) as available_qty,
            expired_date,
            CASE 
                WHEN expired_date < CURDATE() THEN 'EXPIRED'
                WHEN expired_date <= DATE_ADD(CURDATE(), INTERVAL 7 DAY) THEN 'CRITICAL'
                WHEN expired_date <= DATE_ADD(CURDATE(), INTERVAL 30 DAY) THEN 'WARNING'
                ELSE 'OK'
            END as expiry_status
        FROM inventory_histories
        WHERE product_id = %s
        AND warehouse_id = %s
        AND remain > 0
        AND delete_flag = 0
        GROUP BY batch_no, expired_date
        ORDER BY expired_date ASC, batch_no ASC
        """
        
        return pd.read_sql(query, self.engine, params=(product_id, warehouse_id))
    
    def get_batch_info(self, batch_no):
        """Get information about a specific batch"""
        query = """
        SELECT 
            ih.batch_no,
            ih.product_id,
            p.name as product_name,
            p.pt_code as product_code,
            SUM(ih.quantity) as quantity,
            ih.uom,
            ih.expired_date,
            MIN(ih.created_date) as created_date,
            w.name as warehouse
        FROM inventory_histories ih
        JOIN products p ON ih.product_id = p.id
        JOIN warehouses w ON ih.warehouse_id = w.id
        WHERE ih.batch_no = %s
        AND ih.type = 'stockInProduction'
        GROUP BY ih.batch_no, ih.product_id, p.name, p.pt_code, ih.uom, ih.expired_date, w.name
        """
        
        result = pd.read_sql(query, self.engine, params=(batch_no,))
        return result.iloc[0].to_dict() if not result.empty else None
    
    def get_batch_sources(self, batch_no):
        """Get source materials for a batch (genealogy)"""
        query = """
        SELECT 
            p.name as material_name,
            mid.quantity,
            mid.batch_no as source_batch,
            ih_source.expired_date
        FROM production_receipts pr
        JOIN material_issue_details mid ON mid.manufacturing_order_id = pr.manufacturing_order_id
        JOIN products p ON mid.material_id = p.id
        LEFT JOIN inventory_histories ih_source ON ih_source.id = mid.inventory_history_id
        WHERE pr.batch_no = %s
        ORDER BY p.name
        """
        
        return pd.read_sql(query, self.engine, params=(batch_no,))
    
    def get_batch_locations(self, batch_no):
        """Get current locations of a batch"""
        query = """
        SELECT 
            w.name as warehouse,
            SUM(ih.remain) as quantity,
            CASE 
                WHEN ih.expired_date < CURDATE() THEN 'EXPIRED'
                WHEN ih.remain = 0 THEN 'CONSUMED'
                ELSE 'AVAILABLE'
            END as status,
            MAX(ih.updated_date) as last_updated
        FROM inventory_histories ih
        JOIN warehouses w ON ih.warehouse_id = w.id
        WHERE ih.batch_no = %s
        GROUP BY w.name, status
        HAVING quantity > 0
        """
        
        return pd.read_sql(query, self.engine, params=(batch_no,))
    
    def get_batches_by_date(self, start_date, end_date):
        """Get batches created in date range"""
        query = """
        SELECT 
            pr.batch_no,
            pr.receipt_date,
            p.name as product_name,
            pr.quantity,
            pr.quality_status,
            o.order_no,
            b.bom_type
        FROM production_receipts pr
        JOIN products p ON pr.product_id = p.id
        JOIN manufacturing_orders o ON pr.manufacturing_order_id = o.id
        JOIN bom_headers b ON o.bom_header_id = b.id
        WHERE DATE(pr.receipt_date) BETWEEN %s AND %s
        ORDER BY pr.receipt_date DESC
        """
        
        return pd.read_sql(query, self.engine, params=(start_date, end_date))
    
    def get_production_impact(self, start_date, end_date):
        """Get inventory impact from production activities"""
        query = """
        SELECT 
            p.id as product_id,
            p.name as product_name,
            SUM(CASE 
                WHEN ih.type = 'stockInProduction' THEN ih.quantity 
                ELSE 0 
            END) as produced,
            SUM(CASE 
                WHEN ih.type = 'stockOutProduction' THEN -ih.quantity 
                ELSE 0 
            END) as consumed,
            SUM(CASE 
                WHEN ih.type = 'stockInProduction' THEN ih.quantity
                WHEN ih.type = 'stockOutProduction' THEN -ih.quantity
                ELSE 0
            END) as net_change
        FROM inventory_histories ih
        JOIN products p ON ih.product_id = p.id
        WHERE ih.type IN ('stockInProduction', 'stockOutProduction')
        AND DATE(ih.created_date) BETWEEN %s AND %s
        AND ih.delete_flag = 0
        GROUP BY p.id, p.name
        HAVING net_change != 0
        ORDER BY ABS(net_change) DESC
        """
        
        return pd.read_sql(query, self.engine, params=(start_date, end_date))
    
    def get_expiry_status(self, days_ahead=30):
        """Get products by expiry status"""
        query = """
        SELECT 
            p.name as product_name,
            ih.batch_no,
            SUM(ih.remain) as quantity,
            ih.expired_date,
            w.name as warehouse,
            CASE 
                WHEN ih.expired_date < CURDATE() THEN 'EXPIRED'
                WHEN ih.expired_date <= DATE_ADD(CURDATE(), INTERVAL 7 DAY) THEN 'CRITICAL'
                WHEN ih.expired_date <= DATE_ADD(CURDATE(), INTERVAL %s DAY) THEN 'WARNING'
                ELSE 'OK'
            END as expiry_status,
            DATEDIFF(ih.expired_date, CURDATE()) as days_to_expiry
        FROM inventory_histories ih
        JOIN products p ON ih.product_id = p.id
        JOIN warehouses w ON ih.warehouse_id = w.id
        WHERE ih.remain > 0
        AND ih.delete_flag = 0
        AND ih.expired_date <= DATE_ADD(CURDATE(), INTERVAL %s DAY)
        GROUP BY p.name, ih.batch_no, ih.expired_date, w.name
        ORDER BY ih.expired_date ASC
        """
        
        return pd.read_sql(query, self.engine, params=(days_ahead, days_ahead))
    
    def get_warehouses(self):
        """Get list of active warehouses"""
        query = """
        SELECT 
            w.id,
            w.name,
            w.company_id,
            c.english_name as company_name
        FROM warehouses w
        LEFT JOIN companies c ON w.company_id = c.id
        WHERE w.delete_flag = 0
        ORDER BY w.name
        """
        
        return pd.read_sql(query, self.engine)
    
    def get_warehouse_list(self):
        """Get simple warehouse name list"""
        warehouses = self.get_warehouses()
        return warehouses['name'].tolist()
    
    def check_stock_availability(self, materials_df, warehouse_id):
        """Check if materials are available in stock"""
        availability = []
        
        for _, material in materials_df.iterrows():
            stock = self.get_stock_balance(material['material_id'], warehouse_id)
            availability.append({
                'material_id': material['material_id'],
                'material_name': material['material_name'],
                'required': material['required_qty'],
                'available': stock,
                'sufficient': stock >= material['required_qty']
            })
        
        return pd.DataFrame(availability)
    
    def get_low_stock_items(self, threshold_percent=20):
        """Get items below minimum stock level"""
        # Note: min_stock_level not in actual products table
        # This is a simplified version that shows items with low stock
        query = """
        WITH stock_levels AS (
            SELECT 
                p.id,
                p.name as product_name,
                w.name as warehouse,
                COALESCE(SUM(ih.remain), 0) as current_stock
            FROM products p
            CROSS JOIN warehouses w
            LEFT JOIN inventory_histories ih ON ih.product_id = p.id 
                AND ih.warehouse_id = w.id 
                AND ih.remain > 0
                AND ih.delete_flag = 0
            WHERE p.delete_flag = 0
            AND p.approval_status = 1
            AND p.is_service = 0
            AND w.delete_flag = 0
            GROUP BY p.id, p.name, w.id, w.name
            HAVING current_stock < 50  -- Default threshold
        )
        SELECT 
            product_name,
            current_stock,
            50 as min_stock,  -- Default minimum
            (50 - current_stock) as shortage,
            warehouse
        FROM stock_levels
        ORDER BY shortage DESC
        """
        
        return pd.read_sql(query, self.engine)
    
    def preview_fefo_issue(self, product_id, quantity, warehouse_id):
        """Preview which batches would be issued using FEFO"""
        batches = self.get_stock_by_batch(product_id, warehouse_id)
        
        if batches.empty:
            return pd.DataFrame()
        
        remaining_qty = quantity
        selected_batches = []
        
        for _, batch in batches.iterrows():
            if remaining_qty <= 0:
                break
            
            take_qty = min(remaining_qty, batch['available_qty'])
            selected_batches.append({
                'batch_no': batch['batch_no'],
                'quantity': take_qty,
                'expired_date': batch['expired_date'],
                'expiry_status': batch['expiry_status']
            })
            
            remaining_qty -= take_qty
        
        return pd.DataFrame(selected_batches)