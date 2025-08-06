# modules/bom.py - Bill of Materials Management
import pandas as pd
from datetime import datetime
from utils.db import get_db_engine
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


class BOMManager:
    """Manage Bill of Materials operations"""
    
    def __init__(self):
        self.engine = get_db_engine()
    
    def get_boms(self, bom_type=None, status=None, search=None):
        """Get list of BOMs with filters"""
        query = """
        SELECT 
            h.id,
            h.bom_code,
            h.bom_name,
            h.bom_type,
            h.status,
            h.version,
            h.output_qty,
            h.uom,
            h.effective_date,
            h.expiry_date,
            p.name as product_name,
            p.pt_code as product_code,
            u.username as created_by_name,
            h.created_date
        FROM bom_headers h
        JOIN products p ON h.product_id = p.id
        LEFT JOIN users u ON h.created_by = u.id
        WHERE h.delete_flag = 0
        """
        
        params = []
        
        if bom_type:
            query += " AND h.bom_type = %s"
            params.append(bom_type)
        
        if status:
            query += " AND h.status = %s"
            params.append(status)
        
        if search:
            query += """ AND (h.bom_code LIKE %s 
                        OR h.bom_name LIKE %s 
                        OR p.name LIKE %s
                        OR p.pt_code LIKE %s)"""
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern, search_pattern, search_pattern])
        
        query += " ORDER BY h.created_date DESC"
        
        return pd.read_sql(query, self.engine, params=tuple(params) if params else None)
    
    def get_active_boms(self, bom_type=None):
        """Get active BOMs"""
        return self.get_boms(bom_type=bom_type, status='ACTIVE')
    
    def get_bom_info(self, bom_id):
        """Get BOM header information"""
        query = """
        SELECT 
            h.*,
            p.name as product_name,
            p.pt_code as product_code
        FROM bom_headers h
        JOIN products p ON h.product_id = p.id
        WHERE h.id = %s
        """
        
        result = pd.read_sql(query, self.engine, params=(bom_id,))
        return result.iloc[0].to_dict() if not result.empty else None
    
    def get_bom_details(self, bom_id):
        """Get BOM materials"""
        query = """
        SELECT 
            d.id,
            d.material_id,
            d.material_type,
            d.quantity,
            d.uom,
            d.scrap_rate,
            p.name as material_name,
            p.pt_code as material_code
        FROM bom_details d
        JOIN products p ON d.material_id = p.id
        WHERE d.bom_header_id = %s
        ORDER BY d.material_type, p.name
        """
        
        return pd.read_sql(query, self.engine, params=(bom_id,))
    
    def create_bom(self, bom_data):
        """Create new BOM with materials"""
        conn = self.engine.connect()
        trans = conn.begin()
        
        try:
            # Generate BOM code
            bom_code = self._generate_bom_code(bom_data['bom_type'])
            
            # Insert BOM header
            header_query = text("""
            INSERT INTO bom_headers (
                bom_code, bom_name, bom_type, product_id, output_qty, 
                uom, status, version, effective_date, notes, created_by
            ) VALUES (
                :bom_code, :bom_name, :bom_type, :product_id, :output_qty,
                :uom, 'DRAFT', 1, :effective_date, :notes, :created_by
            )
            """)
            
            result = conn.execute(header_query, {
                'bom_code': bom_code,
                'bom_name': bom_data['bom_name'],
                'bom_type': bom_data['bom_type'],
                'product_id': bom_data['product_id'],
                'output_qty': bom_data['output_qty'],
                'uom': bom_data['uom'],
                'effective_date': bom_data['effective_date'],
                'notes': bom_data.get('notes', ''),
                'created_by': bom_data['created_by']
            })
            
            bom_id = result.lastrowid
            
            # Insert BOM details
            if bom_data.get('materials'):
                for material in bom_data['materials']:
                    detail_query = text("""
                    INSERT INTO bom_details (
                        bom_header_id, material_id, material_type, 
                        quantity, uom, scrap_rate
                    ) VALUES (
                        :bom_header_id, :material_id, :material_type,
                        :quantity, :uom, :scrap_rate
                    )
                    """)
                    
                    conn.execute(detail_query, {
                        'bom_header_id': bom_id,
                        'material_id': material['material_id'],
                        'material_type': material['material_type'],
                        'quantity': material['quantity'],
                        'uom': material['uom'],
                        'scrap_rate': material.get('scrap_rate', 0)
                    })
            
            trans.commit()
            logger.info(f"Created BOM {bom_code}")
            return bom_code
            
        except Exception as e:
            trans.rollback()
            logger.error(f"Error creating BOM: {e}")
            raise
        finally:
            conn.close()
    
    def update_bom_status(self, bom_id, new_status, updated_by):
        """Update BOM status"""
        query = text("""
        UPDATE bom_headers 
        SET status = :status, 
            updated_by = :updated_by,
            updated_date = NOW()
        WHERE id = :bom_id
        """)
        
        with self.engine.connect() as conn:
            conn.execute(query, {
                'status': new_status,
                'updated_by': updated_by,
                'bom_id': bom_id
            })
            conn.commit()
    
    def get_material_usage_summary(self):
        """Get summary of material usage across BOMs"""
        query = """
        SELECT 
            p.id as material_id,
            p.name as material_name,
            COUNT(DISTINCT d.bom_header_id) as usage_count,
            SUM(d.quantity) as total_quantity,
            GROUP_CONCAT(DISTINCT h.bom_type) as bom_types
        FROM bom_details d
        JOIN products p ON d.material_id = p.id
        JOIN bom_headers h ON d.bom_header_id = h.id
        WHERE h.delete_flag = 0 AND h.status = 'ACTIVE'
        GROUP BY p.id, p.name
        ORDER BY usage_count DESC, total_quantity DESC
        """
        
        return pd.read_sql(query, self.engine)
    
    def get_where_used(self, product_id):
        """Find where a product is used as material"""
        query = """
        SELECT 
            h.id as bom_id,
            h.bom_code,
            h.bom_name,
            h.status as bom_status,
            p.name as product_name,
            d.quantity,
            d.uom,
            d.material_type
        FROM bom_details d
        JOIN bom_headers h ON d.bom_header_id = h.id
        JOIN products p ON h.product_id = p.id
        WHERE d.material_id = %s
        AND h.delete_flag = 0
        ORDER BY h.status, h.bom_name
        """
        
        return pd.read_sql(query, self.engine, params=(product_id,))
    
    def _generate_bom_code(self, bom_type):
        """Generate unique BOM code"""
        prefix = f"BOM-{bom_type[:3]}"
        
        # Get latest number
        query = """
        SELECT MAX(CAST(SUBSTRING_INDEX(bom_code, '-', -1) AS UNSIGNED)) as max_num
        FROM bom_headers
        WHERE bom_code LIKE %s
        """
        
        result = pd.read_sql(query, self.engine, params=(f"{prefix}-%",))
        
        max_num = result['max_num'].iloc[0] if not result.empty and result['max_num'].iloc[0] else 0
        new_num = (max_num or 0) + 1
        
        return f"{prefix}-{new_num:04d}"