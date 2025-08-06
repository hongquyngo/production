# modules/common.py - Common utility functions
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Dict, Tuple, Any, Optional, Union, List
from io import BytesIO
import streamlit as st
import logging

from utils.db import get_db_engine

logger = logging.getLogger(__name__)


@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_products() -> pd.DataFrame:
    """Get all active products"""
    engine = get_db_engine()
    
    query = """
    SELECT 
        p.id,
        p.name,
        p.pt_code as code,
        p.legacy_pt_code,
        p.description,
        p.package_size,
        p.uom,
        p.shelf_life,
        p.storage_condition,
        b.brand_name as brand,
        p.approval_status
    FROM products p
    LEFT JOIN brands b ON p.brand_id = b.id
    WHERE p.delete_flag = 0
    AND p.approval_status = 1
    AND p.is_service = 0
    ORDER BY p.name
    """
    
    return pd.read_sql(query, engine)


@st.cache_data(ttl=300)
def get_warehouses() -> pd.DataFrame:
    """Get all active warehouses"""
    engine = get_db_engine()
    
    query = """
    SELECT 
        w.id,
        w.name,
        w.address,
        w.company_id,
        c.english_name as company_name,
        CONCAT(e.first_name, ' ', e.last_name) as manager_name
    FROM warehouses w
    LEFT JOIN companies c ON w.company_id = c.id
    LEFT JOIN employees e ON w.manager_id = e.id
    WHERE w.delete_flag = 0
    ORDER BY w.name
    """
    
    return pd.read_sql(query, engine)


def format_number(value: Union[int, float, None], decimal_places: int = 2) -> str:
    """Format number with thousand separators"""
    if pd.isna(value) or value is None:
        return "0"
    return f"{value:,.{decimal_places}f}"


def format_currency(value: Union[int, float, None], currency: str = "VND") -> str:
    """Format currency value"""
    if pd.isna(value) or value is None:
        return f"0 {currency}"
    return f"{value:,.0f} {currency}"


def generate_order_number(prefix: str = "ORD") -> str:
    """Generate unique order number with timestamp"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    return f"{prefix}-{timestamp}"


def calculate_date_range(period: str = "month") -> Tuple[date, date]:
    """Calculate common date ranges"""
    today = date.today()
    
    if period == "today":
        return today, today
    elif period == "week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return start, end
    elif period == "month":
        start = today.replace(day=1)
        if today.month == 12:
            end = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(today.year, today.month + 1, 1) - timedelta(days=1)
        return start, end
    elif period == "quarter":
        quarter = (today.month - 1) // 3
        start = date(today.year, quarter * 3 + 1, 1)
        if quarter == 3:
            end = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(today.year, (quarter + 1) * 3 + 1, 1) - timedelta(days=1)
        return start, end
    elif period == "year":
        start = date(today.year, 1, 1)
        end = date(today.year, 12, 31)
        return start, end
    else:
        return today, today


def validate_quantity(value: Any, min_value: float = 0, max_value: Optional[float] = None) -> Tuple[bool, Union[float, str]]:
    """Validate quantity input"""
    try:
        qty = float(value)
        if qty < min_value:
            return False, f"Quantity must be at least {min_value}"
        if max_value and qty > max_value:
            return False, f"Quantity cannot exceed {max_value}"
        return True, qty
    except (ValueError, TypeError):
        return False, "Invalid quantity format"


def get_status_color(status: str) -> str:
    """Get color for status display"""
    status_colors = {
        'DRAFT': '#808080',
        'CONFIRMED': '#0088FE',
        'IN_PROGRESS': '#FFB800',
        'COMPLETED': '#00CC88',
        'CANCELLED': '#FF4444',
        'ACTIVE': '#00CC88',
        'INACTIVE': '#808080',
        'EXPIRED': '#FF0000',
        'CRITICAL': '#FF4444',
        'WARNING': '#FFB800',
        'OK': '#00CC88',
        'PASSED': '#00CC88',
        'FAILED': '#FF4444',
        'PENDING': '#FFB800'
    }
    return status_colors.get(status.upper(), '#808080')


def create_status_badge(status: str) -> str:
    """Create HTML badge for status"""
    color = get_status_color(status)
    return f'<span style="background-color: {color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">{status}</span>'


@st.cache_data(ttl=60)  # Cache for 1 minute
def get_product_info(product_id: int) -> Optional[Dict[str, Any]]:
    """Get detailed product information"""
    engine = get_db_engine()
    
    query = """
    SELECT 
        p.id,
        p.name,
        p.pt_code as code,
        p.legacy_pt_code,
        p.description,
        p.package_size,
        p.uom,
        p.shelf_life,
        p.shelf_life_uom,
        p.storage_condition,
        b.brand_name as brand,
        COALESCE(SUM(ih.remain), 0) as current_stock
    FROM products p
    LEFT JOIN brands b ON p.brand_id = b.id
    LEFT JOIN inventory_histories ih ON ih.product_id = p.id 
        AND ih.remain > 0 
        AND ih.delete_flag = 0
    WHERE p.id = %s
    GROUP BY p.id, p.name, p.pt_code, p.legacy_pt_code, p.description, 
             p.package_size, p.uom, p.shelf_life, p.shelf_life_uom, 
             p.storage_condition, b.brand_name
    """
    
    result = pd.read_sql(query, engine, params=(product_id,))
    return result.iloc[0].to_dict() if not result.empty else None


def export_to_excel(dataframes_dict: Dict[str, pd.DataFrame], filename: str = "export.xlsx") -> bytes:
    """Export multiple dataframes to Excel file"""
    output = BytesIO()
    
    try:
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            for sheet_name, df in dataframes_dict.items():
                # Excel sheet name limit is 31 characters
                safe_sheet_name = sheet_name[:31]
                df.to_excel(writer, sheet_name=safe_sheet_name, index=False)
                
                # Auto-adjust column widths
                worksheet = writer.sheets[safe_sheet_name]
                for i, col in enumerate(df.columns):
                    column_width = max(df[col].astype(str).str.len().max(), len(col)) + 2
                    worksheet.set_column(i, i, min(column_width, 50))
        
        return output.getvalue()
    except Exception as e:
        logger.error(f"Error exporting to Excel: {e}")
        raise


def show_data_table(df: pd.DataFrame, key: Optional[str] = None, height: int = 400, 
                   selection_mode: str = "single") -> Optional[List[Dict]]:
    """Display interactive data table with AgGrid or fallback to standard dataframe"""
    try:
        from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
        
        gb = GridOptionsBuilder.from_dataframe(df)
        gb.configure_default_column(resizable=True, filterable=True, sortable=True)
        gb.configure_selection(selection_mode=selection_mode)
        gb.configure_pagination(enabled=True, paginationAutoPageSize=True)
        
        grid_options = gb.build()
        
        grid_response = AgGrid(
            df,
            gridOptions=grid_options,
            height=height,
            key=key,
            update_mode=GridUpdateMode.SELECTION_CHANGED
        )
        
        return grid_response['selected_rows']
    
    except (ImportError, ModuleNotFoundError):
        # Fallback to standard dataframe if AgGrid not installed
        st.dataframe(df, use_container_width=True, height=height, key=key)
        return None


def validate_date_range(start_date: date, end_date: date) -> Tuple[bool, Optional[str]]:
    """Validate date range"""
    if start_date > end_date:
        return False, "Start date cannot be after end date"
    
    if (end_date - start_date).days > 365:
        return False, "Date range cannot exceed 1 year"
    
    return True, None


def get_date_filter_presets() -> Dict[str, Tuple[date, date]]:
    """Get common date filter presets"""
    today = date.today()
    
    return {
        "Today": (today, today),
        "Yesterday": (today - timedelta(days=1), today - timedelta(days=1)),
        "This Week": calculate_date_range("week"),
        "Last Week": (today - timedelta(days=today.weekday() + 7), 
                     today - timedelta(days=today.weekday() + 1)),
        "This Month": calculate_date_range("month"),
        "Last Month": ((today.replace(day=1) - timedelta(days=1)).replace(day=1),
                      today.replace(day=1) - timedelta(days=1)),
        "This Quarter": calculate_date_range("quarter"),
        "This Year": calculate_date_range("year"),
        "Last 7 Days": (today - timedelta(days=6), today),
        "Last 30 Days": (today - timedelta(days=29), today),
        "Last 90 Days": (today - timedelta(days=89), today)
    }


def create_download_button(data: Union[pd.DataFrame, Dict[str, pd.DataFrame], str], 
                         filename: str, label: str = "Download", file_type: str = "csv") -> None:
    """Create download button for data export"""
    if file_type == "csv":
        if isinstance(data, pd.DataFrame):
            csv = data.to_csv(index=False)
            mime = "text/csv"
        else:
            csv = data
            mime = "text/csv"
        
        st.download_button(
            label=f"📥 {label}",
            data=csv,
            file_name=filename,
            mime=mime,
            use_container_width=True
        )
    
    elif file_type == "excel":
        try:
            if isinstance(data, dict):
                excel_data = export_to_excel(data, filename)
            else:
                excel_data = export_to_excel({"Sheet1": data}, filename)
            
            st.download_button(
                label=f"📥 {label}",
                data=excel_data,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Error creating Excel file: {str(e)}")


def log_activity(activity_type: str, reference: str, user_id: int, details: Optional[Dict] = None) -> None:
    """Log user activity (placeholder for future implementation)"""
    logger.info(f"Activity: {activity_type} - {reference} by user {user_id}")
    if details:
        logger.debug(f"Details: {details}")


def show_success_message(message: str, duration: int = 3) -> Any:
    """Show success message with auto-hide"""
    placeholder = st.empty()
    placeholder.success(message)
    
    # Auto-hide after duration (requires JavaScript in real implementation)
    # For now, just keep it visible
    return placeholder


def show_error_message(message: str, details: Optional[str] = None) -> None:
    """Show error message with optional details"""
    st.error(message)
    if details:
        with st.expander("Error Details"):
            st.code(details)


def confirm_action(message: str, key: Optional[str] = None) -> Tuple[bool, bool]:
    """Show confirmation dialog (simple version)"""
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.warning(message)
    with col2:
        confirm = st.button("✓ Confirm", key=f"{key}_confirm" if key else None, 
                          type="primary", use_container_width=True)
    with col3:
        cancel = st.button("✗ Cancel", key=f"{key}_cancel" if key else None, 
                         use_container_width=True)
    
    return confirm, cancel


def format_datetime(dt: Union[datetime, str, None], format_string: str = "%Y-%m-%d %H:%M") -> str:
    """Format datetime object"""
    if pd.isna(dt) or dt is None:
        return ""
    
    if isinstance(dt, str):
        try:
            dt = pd.to_datetime(dt)
        except Exception:
            return dt
    
    return dt.strftime(format_string)


def calculate_percentage(numerator: Union[int, float], denominator: Union[int, float], 
                       decimal_places: int = 1) -> float:
    """Calculate percentage safely"""
    if denominator == 0 or pd.isna(denominator) or pd.isna(numerator):
        return 0.0
    
    percentage = (numerator / denominator) * 100
    return round(percentage, decimal_places)


def get_time_ago(dt: Union[datetime, str, None]) -> str:
    """Get human-readable time ago"""
    if pd.isna(dt) or dt is None:
        return "Unknown"
    
    if isinstance(dt, str):
        try:
            dt = pd.to_datetime(dt)
        except Exception:
            return "Unknown"
    
    now = datetime.now()
    if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
        now = now.replace(tzinfo=dt.tzinfo)
    
    diff = now - dt
    
    if diff.days > 365:
        years = diff.days // 365
        return f"{years} year{'s' if years > 1 else ''} ago"
    elif diff.days > 30:
        months = diff.days // 30
        return f"{months} month{'s' if months > 1 else ''} ago"
    elif diff.days > 0:
        return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    else:
        return "Just now"