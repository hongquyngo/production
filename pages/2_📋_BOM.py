# pages/2_📋_BOM.py - Bill of Materials Management
import streamlit as st
import pandas as pd
from datetime import date
import time
from typing import Dict, List, Optional
from utils.auth import AuthManager
from modules.bom import BOMManager
from modules.common import (
    get_products, format_number, create_status_badge, create_status_indicator,
    confirm_action, show_success_message, show_error_message,
    create_download_button
)
import logging

logger = logging.getLogger(__name__)

# Page config
st.set_page_config(
    page_title="BOM Management",
    page_icon="📋",
    layout="wide"
)

# Authentication
auth = AuthManager()
auth.require_auth()

# Initialize BOM manager
bom_manager = BOMManager()

# Page header
st.title("📋 Bill of Materials (BOM) Management")

# Initialize session state
if 'bom_view' not in st.session_state:
    st.session_state.bom_view = 'list'
if 'selected_bom' not in st.session_state:
    st.session_state.selected_bom = None
if 'temp_materials' not in st.session_state:
    st.session_state.temp_materials = []

# Top navigation
col1, col2, col3, col4 = st.columns(4)
with col1:
    if st.button("📋 BOM List", use_container_width=True, 
                type="primary" if st.session_state.bom_view == 'list' else "secondary"):
        st.session_state.bom_view = 'list'
        st.session_state.selected_bom = None
with col2:
    if st.button("➕ Create BOM", use_container_width=True, 
                type="primary" if st.session_state.bom_view == 'create' else "secondary"):
        st.session_state.bom_view = 'create'
        st.session_state.temp_materials = []  # Clear temp materials
with col3:
    if st.button("✏️ Edit BOM", use_container_width=True, 
                type="primary" if st.session_state.bom_view == 'edit' else "secondary"):
        st.session_state.bom_view = 'edit'
with col4:
    if st.button("📊 BOM Analysis", use_container_width=True, 
                type="primary" if st.session_state.bom_view == 'analysis' else "secondary"):
        st.session_state.bom_view = 'analysis'

st.markdown("---")

# Content based on view
if st.session_state.bom_view == 'list':
    # BOM List View
    st.subheader("📋 Bill of Materials List")
    
    # Filters
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        filter_type = st.selectbox("BOM Type", ["All", "KITTING", "CUTTING", "REPACKING"])
    with col2:
        filter_status = st.selectbox("Status", ["All", "DRAFT", "ACTIVE", "INACTIVE"])
    with col3:
        filter_product = st.text_input("Product Name/Code", placeholder="Search...")
    with col4:
        st.markdown("<br>", unsafe_allow_html=True)
        refresh = st.button("🔄 Refresh", use_container_width=True)
    
    # Get BOMs
    boms = bom_manager.get_boms(
        bom_type=None if filter_type == "All" else filter_type,
        status=None if filter_status == "All" else filter_status,
        search=filter_product if filter_product else None
    )
    
    if not boms.empty:
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total BOMs", len(boms))
        with col2:
            active_count = len(boms[boms['status'] == 'ACTIVE'])
            st.metric("Active BOMs", active_count)
        with col3:
            kitting_count = len(boms[boms['bom_type'] == 'KITTING'])
            st.metric("Kitting BOMs", kitting_count)
        with col4:
            draft_count = len(boms[boms['status'] == 'DRAFT'])
            st.metric("Draft BOMs", draft_count)
        
        st.markdown("---")
        
        # Display BOMs
        for idx, bom in boms.iterrows():
            # Create expander with status indicator
            expander_title = f"{bom['bom_code']} - {bom['bom_name']} | {create_status_indicator(bom['status'])}"
            with st.expander(expander_title, expanded=False):
                # Main info columns
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"**Type:** {bom['bom_type']}")
                    st.write(f"**Product:** {bom['product_name']}")
                    st.write(f"**Output:** {format_number(bom['output_qty'])} {bom['uom']}")
                with col2:
                    st.write(f"**Version:** {bom['version']}")
                    st.write(f"**Effective Date:** {bom['effective_date']}")
                    st.write(f"**Created By:** {bom['created_by_name'] or 'System'}")
                with col3:
                    action_col1, action_col2 = st.columns(2)
                    with action_col1:
                        if st.button("👁️ View", key=f"view_{bom['id']}", use_container_width=True):
                            st.session_state.selected_bom = bom['id']
                            st.session_state.bom_view = 'edit'
                            st.rerun()
                    with action_col2:
                        if bom['status'] == 'ACTIVE':
                            if st.button("📋 Copy", key=f"copy_{bom['id']}", use_container_width=True):
                                st.info("Copy BOM feature coming soon!")
                
                # Get and display BOM details
                details = bom_manager.get_bom_details(bom['id'])
                if not details.empty:
                    st.markdown("**Materials:**")
                    # Calculate total cost if possible
                    details['total_qty'] = details['quantity'] * (1 + details['scrap_rate']/100)
                    
                    st.dataframe(
                        details[['material_name', 'material_type', 'quantity', 'uom', 'scrap_rate', 'total_qty']],
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "material_name": "Material",
                            "material_type": "Type",
                            "quantity": st.column_config.NumberColumn("Qty", format="%.4f"),
                            "uom": "UOM",
                            "scrap_rate": st.column_config.NumberColumn("Scrap %", format="%.1f"),
                            "total_qty": st.column_config.NumberColumn("Total Qty", format="%.4f")
                        }
                    )
        
        # Export button
        if st.button("📥 Export to Excel", use_container_width=True):
            excel_data = {
                "BOM List": boms[['bom_code', 'bom_name', 'bom_type', 'product_name', 
                                 'output_qty', 'uom', 'status', 'version', 'effective_date']]
            }
            create_download_button(
                excel_data,
                f"BOM_List_{date.today()}.xlsx",
                "Download BOM List",
                "excel"
            )
    else:
        st.info("No BOMs found matching the criteria")

elif st.session_state.bom_view == 'create':
    # Create New BOM
    st.subheader("➕ Create New BOM")
    
    # Basic Information
    st.markdown("### Basic Information")
    col1, col2 = st.columns(2)
    
    with col1:
        bom_name = st.text_input("BOM Name*", placeholder="e.g., Standard Kit A")
        bom_type = st.selectbox("BOM Type*", ["KITTING", "CUTTING", "REPACKING"])
        
        # Get products
        products = get_products()
        if not products.empty:
            product_options = dict(zip(
                products['name'] + " (" + products['code'] + ")", 
                products['id']
            ))
            selected_product = st.selectbox("Output Product*", options=list(product_options.keys()))
            product_id = product_options[selected_product] if selected_product else None
        else:
            st.error("No products found. Please add products first.")
            product_id = None
        
    with col2:
        output_qty = st.number_input("Output Quantity*", min_value=0.01, value=1.0, step=0.01)
        uom = st.text_input("UOM*", value="PCS")
        effective_date = st.date_input("Effective Date*", value=date.today())
    
    # Materials Section (Outside of form for better interaction)
    st.markdown("### Materials")
    
    # Add material controls
    col1, col2, col3, col4, col5, col6 = st.columns([3, 1.5, 1, 1.5, 1, 1])
    with col1:
        material_select = st.selectbox(
            "Select Material",
            options=[""] + list(product_options.keys()) if products is not None else [""],
            key="new_material_select"
        )
    with col2:
        material_qty = st.number_input("Quantity", min_value=0.0001, value=1.0, step=0.0001, key="new_material_qty")
    with col3:
        material_uom = st.text_input("UOM", value="PCS", key="new_material_uom")
    with col4:
        material_type = st.selectbox("Type", ["RAW_MATERIAL", "PACKAGING", "CONSUMABLE"], key="new_material_type")
    with col5:
        scrap_rate = st.number_input("Scrap %", min_value=0.0, max_value=100.0, value=0.0, step=0.1, key="new_scrap_rate")
    with col6:
        if st.button("➕ Add", use_container_width=True, type="primary"):
            if material_select and material_select != "":
                material_id = product_options[material_select]
                # Check if material already exists
                existing = [m for m in st.session_state.temp_materials if m['material_id'] == material_id]
                if existing:
                    st.warning("Material already added. Please remove it first if you want to update.")
                else:
                    st.session_state.temp_materials.append({
                        'material_id': material_id,
                        'material_name': material_select.split(" (")[0],
                        'quantity': material_qty,
                        'uom': material_uom,
                        'material_type': material_type,
                        'scrap_rate': scrap_rate
                    })
                    st.success("Material added!")
                    st.rerun()
            else:
                st.error("Please select a material")
    
    # Display current materials
    if st.session_state.temp_materials:
        st.markdown("**Current Materials:**")
        
        # Create DataFrame for display
        materials_df = pd.DataFrame(st.session_state.temp_materials)
        
        # Add remove buttons
        for idx, material in enumerate(st.session_state.temp_materials):
            col1, col2, col3, col4, col5, col6 = st.columns([3, 1.5, 1, 1.5, 1, 1])
            with col1:
                st.text(material['material_name'])
            with col2:
                st.text(f"{material['quantity']:.4f}")
            with col3:
                st.text(material['uom'])
            with col4:
                st.text(material['material_type'])
            with col5:
                st.text(f"{material['scrap_rate']:.1f}%")
            with col6:
                if st.button("🗑️", key=f"remove_{idx}", use_container_width=True):
                    st.session_state.temp_materials.pop(idx)
                    st.rerun()
        
        # Clear all button
        if st.button("🗑️ Clear All Materials", type="secondary"):
            if confirm_action("Are you sure you want to clear all materials?", "clear_materials")[0]:
                st.session_state.temp_materials = []
                st.rerun()
    else:
        st.info("No materials added yet. Add at least one material to create BOM.")
    
    # Notes
    st.markdown("### Additional Information")
    notes = st.text_area("Notes", height=100, placeholder="Optional notes about this BOM...")
    
    # Submit buttons
    st.markdown("---")
    col1, col2, col3 = st.columns([2, 1, 2])
    with col2:
        create_btn = st.button("Create BOM", type="primary", use_container_width=True, 
                              disabled=not st.session_state.temp_materials)
    
    if create_btn:
        # Validate inputs
        errors = []
        if not bom_name:
            errors.append("BOM Name is required")
        if not product_id:
            errors.append("Output Product is required")
        if not st.session_state.temp_materials:
            errors.append("At least one material is required")
        
        if errors:
            for error in errors:
                st.error(error)
        else:
            try:
                # Create BOM data
                bom_data = {
                    'bom_name': bom_name,
                    'bom_type': bom_type,
                    'product_id': product_id,
                    'output_qty': output_qty,
                    'uom': uom,
                    'effective_date': effective_date,
                    'notes': notes,
                    'materials': st.session_state.temp_materials,
                    'created_by': st.session_state.user_id
                }
                
                # Create BOM
                with st.spinner("Creating BOM..."):
                    bom_code = bom_manager.create_bom(bom_data)
                
                show_success_message(f"✅ BOM {bom_code} created successfully!")
                st.balloons()
                
                # Clear temp materials and redirect
                st.session_state.temp_materials = []
                time.sleep(2)
                st.session_state.bom_view = 'list'
                st.rerun()
                
            except Exception as e:
                show_error_message(f"Error creating BOM", str(e))
                logger.error(f"Error creating BOM: {e}")

elif st.session_state.bom_view == 'edit':
    # Edit BOM
    st.subheader("✏️ View/Edit BOM")
    
    # BOM selection if not already selected
    if not st.session_state.selected_bom:
        boms = bom_manager.get_boms()  # Get all BOMs for selection
        if not boms.empty:
            col1, col2 = st.columns([3, 1])
            with col1:
                bom_options = dict(zip(
                    boms['bom_code'] + " - " + boms['bom_name'] + " | " + 
                    boms['status'].apply(create_status_indicator), 
                    boms['id']
                ))
                selected = st.selectbox("Select BOM to View/Edit", options=list(bom_options.keys()))
            with col2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Load BOM", type="primary", use_container_width=True):
                    st.session_state.selected_bom = bom_options[selected]
                    st.rerun()
        else:
            st.info("No BOMs found")
            if st.button("Go to Create BOM"):
                st.session_state.bom_view = 'create'
                st.rerun()
    else:
        # Load BOM details
        try:
            bom_info = bom_manager.get_bom_info(st.session_state.selected_bom)
            bom_details = bom_manager.get_bom_details(st.session_state.selected_bom)
            
            if not bom_info:
                st.error("BOM not found")
                st.session_state.selected_bom = None
                st.rerun()
            
            # Display BOM header info
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("BOM Code", bom_info['bom_code'])
            with col2:
                st.metric("Status", create_status_indicator(bom_info['status']))
            with col3:
                st.metric("Version", bom_info['version'])
            with col4:
                st.metric("Type", bom_info['bom_type'])
            
            # BOM Information
            st.markdown(f"### {bom_info['bom_name']}")
            
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Output Product:** {bom_info['product_name']}")
                st.write(f"**Output Quantity:** {format_number(bom_info['output_qty'])} {bom_info['uom']}")
                st.write(f"**Effective Date:** {bom_info['effective_date']}")
            with col2:
                st.write(f"**Expiry Date:** {bom_info['expiry_date'] or 'None'}")
                st.write(f"**Created Date:** {bom_info['created_date']}")
                st.write(f"**Notes:** {bom_info.get('notes', 'None')}")
            
            # Materials
            st.markdown("### Materials")
            if not bom_details.empty:
                # Add calculated columns
                bom_details['total_qty'] = bom_details['quantity'] * (1 + bom_details['scrap_rate']/100)
                
                st.dataframe(
                    bom_details[['material_name', 'material_code', 'material_type', 
                               'quantity', 'uom', 'scrap_rate', 'total_qty']],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "material_name": "Material",
                        "material_code": "Code",
                        "material_type": "Type",
                        "quantity": st.column_config.NumberColumn("Base Qty", format="%.4f"),
                        "uom": "UOM",
                        "scrap_rate": st.column_config.NumberColumn("Scrap %", format="%.1f"),
                        "total_qty": st.column_config.NumberColumn("Total Qty", format="%.4f")
                    }
                )
                
                # Export materials button
                if st.button("📥 Export Materials List"):
                    create_download_button(
                        bom_details,
                        f"BOM_Materials_{bom_info['bom_code']}_{date.today()}.csv",
                        "Download Materials",
                        "csv"
                    )
            else:
                st.warning("No materials found for this BOM")
            
            # Actions
            st.markdown("### Actions")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                new_status = st.selectbox(
                    "Change Status", 
                    ["DRAFT", "ACTIVE", "INACTIVE"], 
                    index=["DRAFT", "ACTIVE", "INACTIVE"].index(bom_info['status'])
                )
                if st.button("Update Status", use_container_width=True, type="primary"):
                    if new_status != bom_info['status']:
                        try:
                            bom_manager.update_bom_status(
                                st.session_state.selected_bom, 
                                new_status, 
                                st.session_state.user_id
                            )
                            show_success_message(f"✅ BOM status updated to {new_status}")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            show_error_message("Error updating BOM status", str(e))
                    else:
                        st.info("Status unchanged")
            
            with col2:
                if st.button("📋 Create New Version", use_container_width=True):
                    st.info("This feature will be available soon")
            
            with col3:
                if bom_info['status'] != 'INACTIVE':
                    if st.button("🚫 Deactivate BOM", use_container_width=True, type="secondary"):
                        if confirm_action("Are you sure you want to deactivate this BOM?", "deactivate_bom")[0]:
                            try:
                                bom_manager.update_bom_status(
                                    st.session_state.selected_bom, 
                                    'INACTIVE', 
                                    st.session_state.user_id
                                )
                                show_success_message("✅ BOM deactivated successfully!")
                                time.sleep(1)
                                st.session_state.selected_bom = None
                                st.session_state.bom_view = 'list'
                                st.rerun()
                            except Exception as e:
                                show_error_message("Error deactivating BOM", str(e))
            
            with col4:
                if st.button("← Back to List", use_container_width=True):
                    st.session_state.selected_bom = None
                    st.session_state.bom_view = 'list'
                    st.rerun()
                    
        except Exception as e:
            show_error_message("Error loading BOM", str(e))
            logger.error(f"Error loading BOM: {e}")
            st.session_state.selected_bom = None

elif st.session_state.bom_view == 'analysis':
    # BOM Analysis
    st.subheader("📊 BOM Analysis")
    
    # Analysis options
    analysis_type = st.selectbox(
        "Select Analysis Type",
        ["Material Usage Summary", "Where Used Analysis", "BOM Comparison", "Cost Analysis"]
    )
    
    if analysis_type == "Material Usage Summary":
        st.markdown("### Material Usage Analysis")
        
        with st.spinner("Analyzing material usage..."):
            material_usage = bom_manager.get_material_usage_summary()
        
        if not material_usage.empty:
            # Summary metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Materials", len(material_usage))
            with col2:
                st.metric("Avg Usage per Material", f"{material_usage['usage_count'].mean():.1f} BOMs")
            with col3:
                st.metric("Most Used Material", material_usage.iloc[0]['material_name'])
            
            # Display top used materials chart
            st.markdown("**Top 10 Most Used Materials**")
            top_materials = material_usage.nlargest(10, 'usage_count')
            
            # Create bar chart
            chart_data = top_materials.set_index('material_name')[['usage_count']]
            st.bar_chart(chart_data)
            
            # Detailed table
            st.markdown("**Detailed Material Usage**")
            st.dataframe(
                material_usage,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "material_name": "Material",
                    "usage_count": st.column_config.NumberColumn("Used in # BOMs", format="%d"),
                    "total_quantity": st.column_config.NumberColumn("Total Quantity", format="%.2f"),
                    "bom_types": "BOM Types"
                }
            )
            
            # Export button
            if st.button("📥 Export Material Usage Report"):
                create_download_button(
                    material_usage,
                    f"Material_Usage_Report_{date.today()}.csv",
                    "Download Report",
                    "csv"
                )
        else:
            st.info("No material usage data found")
    
    elif analysis_type == "Where Used Analysis":
        st.markdown("### Where Used Analysis")
        st.write("Find all BOMs where a specific product/material is used")
        
        # Select product
        products = get_products()
        if not products.empty:
            product_options = dict(zip(
                products['name'] + " (" + products['code'] + ")", 
                products['id']
            ))
            
            col1, col2 = st.columns([3, 1])
            with col1:
                selected_product = st.selectbox(
                    "Select Product/Material", 
                    options=list(product_options.keys())
                )
            with col2:
                st.markdown("<br>", unsafe_allow_html=True)
                analyze_btn = st.button("Analyze", type="primary", use_container_width=True)
            
            if analyze_btn and selected_product:
                product_id = product_options[selected_product]
                
                with st.spinner("Searching BOMs..."):
                    where_used = bom_manager.get_where_used(product_id)
                
                if not where_used.empty:
                    st.success(f"**{selected_product} is used in {len(where_used)} BOM(s):**")
                    
                    # Group by BOM status
                    active_boms = where_used[where_used['bom_status'] == 'ACTIVE']
                    inactive_boms = where_used[where_used['bom_status'] != 'ACTIVE']
                    
                    if not active_boms.empty:
                        st.markdown("**Active BOMs:**")
                        st.dataframe(
                            active_boms[['bom_code', 'bom_name', 'product_name', 
                                       'quantity', 'uom', 'material_type']],
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "bom_code": "BOM Code",
                                "bom_name": "BOM Name",
                                "product_name": "Output Product",
                                "quantity": st.column_config.NumberColumn("Qty Required", format="%.4f"),
                                "uom": "UOM",
                                "material_type": "Usage Type"
                            }
                        )
                    
                    if not inactive_boms.empty:
                        with st.expander("Inactive BOMs"):
                            st.dataframe(
                                inactive_boms[['bom_code', 'bom_name', 'bom_status', 
                                             'quantity', 'uom']],
                                use_container_width=True,
                                hide_index=True
                            )
                    
                    # Export button
                    if st.button("📥 Export Where Used Report"):
                        create_download_button(
                            where_used,
                            f"Where_Used_{selected_product.split(' (')[0]}_{date.today()}.csv",
                            "Download Report",
                            "csv"
                        )
                else:
                    st.info(f"{selected_product} is not used in any BOM")
        else:
            st.error("No products found in the system")
    
    elif analysis_type == "BOM Comparison":
        st.markdown("### BOM Comparison")
        st.info("This feature allows you to compare materials between different BOMs. Coming soon!")
    
    elif analysis_type == "Cost Analysis":
        st.markdown("### BOM Cost Analysis")
        st.info("This feature will calculate BOM costs based on material prices. Coming soon!")

# Footer
st.markdown("---")
st.caption("BOM Management System v1.0")