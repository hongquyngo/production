# pages/1_🏭_Production.py - Production Management Page
import streamlit as st
import pandas as pd
from datetime import datetime, date
import time
from utils.auth import AuthManager
from utils.db import get_db_engine
from modules.production import ProductionManager
from modules.inventory import InventoryManager
from modules.bom import BOMManager
import logging

logger = logging.getLogger(__name__)

# Page config
st.set_page_config(
    page_title="Production Management",
    page_icon="🏭",
    layout="wide"
)

# Authentication
auth = AuthManager()
auth.require_auth()

# Initialize managers
prod_manager = ProductionManager()
inv_manager = InventoryManager()
bom_manager = BOMManager()

# Page header
st.title("🏭 Production Management")

# Initialize session state
if 'current_view' not in st.session_state:
    st.session_state.current_view = 'list'
if 'selected_order' not in st.session_state:
    st.session_state.selected_order = None

# Top navigation
col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 2])
with col1:
    if st.button("📋 Order List", use_container_width=True, type="primary" if st.session_state.current_view == 'list' else "secondary"):
        st.session_state.current_view = 'list'
with col2:
    if st.button("➕ New Order", use_container_width=True, type="primary" if st.session_state.current_view == 'new' else "secondary"):
        st.session_state.current_view = 'new'
with col3:
    if st.button("📦 Material Issue", use_container_width=True, type="primary" if st.session_state.current_view == 'issue' else "secondary"):
        st.session_state.current_view = 'issue'
with col4:
    if st.button("✅ Complete Order", use_container_width=True, type="primary" if st.session_state.current_view == 'complete' else "secondary"):
        st.session_state.current_view = 'complete'
with col5:
    if st.button("📊 Dashboard", use_container_width=True, type="primary" if st.session_state.current_view == 'dashboard' else "secondary"):
        st.session_state.current_view = 'dashboard'

st.markdown("---")

# Content based on view
if st.session_state.current_view == 'list':
    # Production Order List
    st.subheader("📋 Production Orders")
    
    # Filters
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        filter_status = st.selectbox("Status", ["All", "DRAFT", "CONFIRMED", "IN_PROGRESS", "COMPLETED", "CANCELLED"])
    with col2:
        filter_type = st.selectbox("Type", ["All", "KITTING", "CUTTING", "REPACKING"])
    with col3:
        filter_from = st.date_input("From Date", value=date.today().replace(day=1))
    with col4:
        filter_to = st.date_input("To Date", value=date.today())
    
    # Get orders
    orders = prod_manager.get_orders(
        status=None if filter_status == "All" else filter_status,
        order_type=None if filter_type == "All" else filter_type,
        from_date=filter_from,
        to_date=filter_to
    )
    
    if not orders.empty:
        # Display orders
        st.dataframe(
            orders,
            use_container_width=True,
            hide_index=True,
            column_config={
                "order_no": "Order No.",
                "order_date": st.column_config.DateColumn("Date"),
                "bom_type": "Type",
                "product_name": "Product",
                "planned_qty": st.column_config.NumberColumn("Planned", format="%d"),
                "produced_qty": st.column_config.NumberColumn("Produced", format="%d"),
                "status": st.column_config.TextColumn("Status"),
                "scheduled_date": st.column_config.DateColumn("Scheduled"),
            }
        )
        
        # Quick actions
        st.markdown("### Quick Actions")
        col1, col2 = st.columns(2)
        with col1:
            order_no = st.selectbox("Select Order", orders['order_no'].tolist())
        with col2:
            action = st.selectbox("Action", ["View Details", "Issue Materials", "Complete Production", "Cancel Order"])
        
        if st.button("Execute Action", type="primary"):
            st.session_state.selected_order = order_no
            if action == "Issue Materials":
                st.session_state.current_view = 'issue'
            elif action == "Complete Production":
                st.session_state.current_view = 'complete'
            st.rerun()
    else:
        st.info("No production orders found for the selected criteria")

elif st.session_state.current_view == 'new':
    # Create New Production Order
    st.subheader("➕ Create New Production Order")
    
    with st.form("new_production_order"):
        col1, col2 = st.columns(2)
        
        with col1:
            # Production type
            prod_type = st.selectbox(
                "Production Type",
                ["KITTING", "CUTTING", "REPACKING"],
                help="Select the type of production"
            )
            
            # Get BOMs for selected type
            boms = bom_manager.get_active_boms(bom_type=prod_type)
            
            if not boms.empty:
                bom_options = dict(zip(boms['bom_name'] + " (" + boms['bom_code'] + ")", boms['id']))
                selected_bom = st.selectbox("Select BOM", options=list(bom_options.keys()))
                bom_id = bom_options[selected_bom]
                
                # Get BOM details
                bom_details = bom_manager.get_bom_details(bom_id)
                bom_info = bom_manager.get_bom_info(bom_id)
                
                # Show BOM info
                st.info(f"**Output:** {bom_info['product_name']} - {bom_info['output_qty']} {bom_info['uom']}")
            else:
                st.warning(f"No active BOMs found for {prod_type}")
                bom_id = None
            
            # Quantity to produce
            qty = st.number_input("Quantity to Produce", min_value=1, value=1, step=1)
            
            # Scheduled date
            scheduled_date = st.date_input("Scheduled Date", value=date.today())
        
        with col2:
            # Warehouse selection
            warehouses = inv_manager.get_warehouses()
            warehouse_options = dict(zip(warehouses['name'], warehouses['id']))
            
            source_warehouse = st.selectbox("Source Warehouse", options=list(warehouse_options.keys()))
            source_warehouse_id = warehouse_options[source_warehouse]
            
            target_warehouse = st.selectbox("Target Warehouse", options=list(warehouse_options.keys()), index=0)
            target_warehouse_id = warehouse_options[target_warehouse]
            
            # Priority
            priority = st.selectbox("Priority", ["LOW", "NORMAL", "HIGH", "URGENT"], index=1)
            
            # Notes
            notes = st.text_area("Notes", height=100)
        
        # Material availability check
        if bom_id and st.form_submit_button("Check Material Availability", type="secondary"):
            st.markdown("### Material Requirements")
            
            # Calculate requirements
            requirements = prod_manager.calculate_material_requirements(bom_id, qty)
            
            # Check availability
            availability = []
            for _, row in requirements.iterrows():
                stock = inv_manager.get_stock_balance(row['material_id'], source_warehouse_id)
                availability.append({
                    'Material': row['material_name'],
                    'Required': row['required_qty'],
                    'Available': stock,
                    'Status': '✅ OK' if stock >= row['required_qty'] else '❌ Insufficient'
                })
            
            availability_df = pd.DataFrame(availability)
            st.dataframe(availability_df, use_container_width=True, hide_index=True)
        
        # Submit button
        col1, col2, col3 = st.columns([2, 1, 2])
        with col2:
            submitted = st.form_submit_button("Create Order", type="primary", use_container_width=True)
        
        if submitted and bom_id:
            try:
                # Create order data
                order_data = {
                    'bom_header_id': bom_id,
                    'product_id': bom_info['product_id'],
                    'planned_qty': qty,
                    'uom': bom_info['uom'],
                    'warehouse_id': source_warehouse_id,
                    'target_warehouse_id': target_warehouse_id,
                    'scheduled_date': scheduled_date,
                    'priority': priority,
                    'notes': notes,
                    'created_by': st.session_state.user_id
                }
                
                # Create order
                order_no = prod_manager.create_order(order_data)
                st.success(f"✅ Production Order {order_no} created successfully!")
                st.balloons()
                
                # Reset view
                st.session_state.current_view = 'list'
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ Error creating order: {str(e)}")

elif st.session_state.current_view == 'issue':
    # Material Issue
    st.subheader("📦 Material Issue")
    
    # Get pending orders
    pending_orders = prod_manager.get_orders(status='CONFIRMED')
    
    if not pending_orders.empty:
        # Order selection
        order_options = dict(zip(
            pending_orders['order_no'] + " - " + pending_orders['product_name'],
            pending_orders['id']
        ))
        
        selected_order_display = st.selectbox("Select Production Order", options=list(order_options.keys()))
        selected_order_id = order_options[selected_order_display]
        
        # Get order details
        order_info = prod_manager.get_order_details(selected_order_id)
        materials = prod_manager.get_order_materials(selected_order_id)
        
        # Display order info
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Product", order_info['product_name'])
        with col2:
            st.metric("Quantity", f"{order_info['planned_qty']} {order_info['uom']}")
        with col3:
            st.metric("Warehouse", order_info['warehouse_name'])
        
        # Materials to issue
        st.markdown("### Materials to Issue")
        
        # Check current status
        materials_with_status = []
        for _, mat in materials.iterrows():
            status = "✅ Issued" if mat['issued_qty'] >= mat['required_qty'] else "⏳ Pending"
            materials_with_status.append({
                'Material': mat['material_name'],
                'Required': mat['required_qty'],
                'Issued': mat['issued_qty'],
                'Remaining': mat['required_qty'] - mat['issued_qty'],
                'Status': status
            })
        
        materials_df = pd.DataFrame(materials_with_status)
        st.dataframe(materials_df, use_container_width=True, hide_index=True)
        
        # Issue materials button
        if any(mat['Status'] == '⏳ Pending' for mat in materials_with_status):
            if st.button("📤 Issue All Materials", type="primary"):
                with st.spinner("Issuing materials..."):
                    try:
                        # Create material issue
                        issue_result = prod_manager.issue_materials(
                            selected_order_id,
                            st.session_state.user_id
                        )
                        
                        st.success(f"✅ Materials issued successfully! Issue No: {issue_result['issue_no']}")
                        
                        # Show issued details
                        st.markdown("### Issued Details")
                        for detail in issue_result['details']:
                            st.write(f"- {detail['material_name']}: {detail['quantity']} {detail['uom']}")
                        
                        # Update order status
                        prod_manager.update_order_status(selected_order_id, 'IN_PROGRESS')
                        
                        time.sleep(2)
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Error issuing materials: {str(e)}")
        else:
            st.info("✅ All materials have been issued for this order")
    else:
        st.info("No confirmed orders pending material issue")

elif st.session_state.current_view == 'complete':
    # Complete Production
    st.subheader("✅ Complete Production")
    
    # Get in-progress orders
    in_progress = prod_manager.get_orders(status='IN_PROGRESS')
    
    if not in_progress.empty:
        # Order selection
        order_options = dict(zip(
            in_progress['order_no'] + " - " + in_progress['product_name'],
            in_progress['id']
        ))
        
        selected_order_display = st.selectbox("Select Production Order", options=list(order_options.keys()))
        selected_order_id = order_options[selected_order_display]
        
        # Get order details
        order_info = prod_manager.get_order_details(selected_order_id)
        
        # Display order info
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Product", order_info['product_name'])
        with col2:
            st.metric("Planned Qty", f"{order_info['planned_qty']} {order_info['uom']}")
        with col3:
            st.metric("Type", order_info['bom_type'])
        with col4:
            st.metric("Target Warehouse", order_info['target_warehouse_name'])
        
        # Production completion form
        with st.form("complete_production"):
            st.markdown("### Production Results")
            
            col1, col2 = st.columns(2)
            with col1:
                produced_qty = st.number_input(
                    "Produced Quantity",
                    min_value=0,
                    max_value=int(order_info['planned_qty']),
                    value=int(order_info['planned_qty']),
                    step=1
                )
                
                batch_no = st.text_input(
                    "Batch Number",
                    value=f"{order_info['bom_type'][:3]}-{datetime.now().strftime('%Y%m%d%H%M')}"
                )
            
            with col2:
                quality_status = st.selectbox("Quality Status", ["PASSED", "FAILED", "PENDING"])
                
                notes = st.text_area("Production Notes", height=100)
            
            # For kitting, show expiry date calculation
            if order_info['bom_type'] == 'KITTING':
                st.info("ℹ️ Kit will inherit the shortest expiry date from its components")
            
            submitted = st.form_submit_button("Complete Production", type="primary")
            
            if submitted:
                try:
                    # Create production receipt
                    receipt_result = prod_manager.complete_production(
                        order_id=selected_order_id,
                        produced_qty=produced_qty,
                        batch_no=batch_no,
                        quality_status=quality_status,
                        notes=notes,
                        created_by=st.session_state.user_id
                    )
                    
                    st.success(f"✅ Production completed! Receipt No: {receipt_result['receipt_no']}")
                    st.balloons()
                    
                    # Show summary
                    st.markdown("### Production Summary")
                    st.write(f"- **Product:** {order_info['product_name']}")
                    st.write(f"- **Quantity:** {produced_qty} {order_info['uom']}")
                    st.write(f"- **Batch:** {batch_no}")
                    st.write(f"- **Location:** {order_info['target_warehouse_name']}")
                    
                    time.sleep(2)
                    st.session_state.current_view = 'list'
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Error completing production: {str(e)}")
    else:
        st.info("No orders in progress")

elif st.session_state.current_view == 'dashboard':
    # Production Dashboard
    st.subheader("📊 Production Dashboard")
    
    # Date range
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("From", value=date.today().replace(day=1))
    with col2:
        end_date = st.date_input("To", value=date.today())
    
    # Get statistics
    stats = prod_manager.get_production_stats(start_date, end_date)
    
    # Display metrics with None value handling
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Orders", stats.get('total_orders', 0) or 0)
    with col2:
        st.metric("Completed", stats.get('completed_orders', 0) or 0)
    with col3:
        st.metric("In Progress", stats.get('in_progress_orders', 0) or 0)
    with col4:
        completion_rate = stats.get('completion_rate', 0) or 0
        st.metric("Completion Rate", f"{completion_rate:.1f}%")
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        # Orders by type
        st.markdown("### Orders by Type")
        type_data = prod_manager.get_orders_by_type(start_date, end_date)
        if not type_data.empty:
            st.bar_chart(type_data.set_index('bom_type')['count'])
        else:
            st.info("No data available")
    
    with col2:
        # Orders by status
        st.markdown("### Orders by Status")
        status_data = prod_manager.get_orders_by_status(start_date, end_date)
        if not status_data.empty:
            st.bar_chart(status_data.set_index('status')['count'])
        else:
            st.info("No data available")
    
    # Recent activities
    st.markdown("### Recent Production Activities")
    recent = prod_manager.get_recent_activities(limit=10)
    if not recent.empty:
        st.dataframe(recent, use_container_width=True, hide_index=True)
    else:
        st.info("No recent activities")