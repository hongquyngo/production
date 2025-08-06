# app.py - Manufacturing Module Main Entry Point
import streamlit as st
from utils.auth import AuthManager
from utils.config import config
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="Manufacturing Module - iSCM",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 1rem;
        color: #1f77b4;
    }
    .info-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #f0f2f6;
        margin-bottom: 1rem;
    }
    .stButton>button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# Initialize authentication manager
auth = AuthManager()

# Check if user is logged in
if not auth.check_session():
    # Login Page
    st.markdown('<p class="main-header">🏭 Manufacturing Module</p>', unsafe_allow_html=True)
    st.markdown("### Please login to continue")
    
    # Center the login form
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.form("login_form", clear_on_submit=True):
            st.markdown("#### Login")
            username = st.text_input("Username", placeholder="Enter your username")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                submit = st.form_submit_button("🔐 Login", type="primary", use_container_width=True)
            with col_btn2:
                st.form_submit_button("🔄 Clear", use_container_width=True)
            
            if submit:
                if username and password:
                    with st.spinner("Authenticating..."):
                        success, user_info = auth.authenticate(username, password)
                        
                    if success:
                        auth.login(user_info)
                        st.success("Login successful! Redirecting...")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error(user_info.get("error", "Authentication failed"))
                else:
                    st.warning("Please enter both username and password")
        
        # Login help
        with st.expander("ℹ️ Login Help"):
            st.info("""
            - Use your iSCM credentials to login
            - Contact IT support if you forgot your password
            - Session expires after 8 hours of inactivity
            """)
else:
    # Main Application (when logged in)
    st.markdown('<p class="main-header">🏭 Manufacturing Module</p>', unsafe_allow_html=True)
    
    # User info in sidebar
    with st.sidebar:
        st.markdown(f"### 👤 {auth.get_user_display_name()}")
        st.markdown(f"**Role:** {st.session_state.user_role}")
        st.markdown(f"**User:** {st.session_state.username}")
        st.markdown("---")
        
        # Navigation help
        st.markdown("### 📍 Navigation")
        st.info("Use the pages below to navigate through different modules")
        
        # Logout button at bottom
        st.markdown("---")
        if st.button("🚪 Logout", use_container_width=True):
            auth.logout()
            st.rerun()
    
    # Main content area
    st.markdown("## Welcome to Manufacturing Module")
    
    # Quick stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            label="🏭 Active Production Orders",
            value="12",
            delta="3 new today"
        )
    with col2:
        st.metric(
            label="📦 Pending Material Issues",
            value="5",
            delta="-2 vs yesterday"
        )
    with col3:
        st.metric(
            label="✅ Completed Today",
            value="8",
            delta="60% completion rate"
        )
    with col4:
        st.metric(
            label="⚠️ Low Stock Items",
            value="3",
            delta="Requires attention"
        )
    
    st.markdown("---")
    
    # Quick actions
    st.markdown("### 🚀 Quick Actions")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown('<div class="info-box">', unsafe_allow_html=True)
        st.markdown("#### 📋 Production")
        st.markdown("Create and manage production orders for kitting, cutting, and repacking")
        if st.button("Go to Production →", key="btn_production"):
            st.switch_page("pages/1_🏭_Production.py")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown('<div class="info-box">', unsafe_allow_html=True)
        st.markdown("#### 📑 BOM Management")
        st.markdown("Define and maintain Bill of Materials for your products")
        if st.button("Manage BOMs →", key="btn_bom"):
            st.switch_page("pages/2_📋_BOM.py")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col3:
        st.markdown('<div class="info-box">', unsafe_allow_html=True)
        st.markdown("#### 📊 Reports")
        st.markdown("View production analytics and inventory reports")
        if st.button("View Reports →", key="btn_reports"):
            st.switch_page("pages/3_📊_Reports.py")
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Recent activities
    st.markdown("---")
    st.markdown("### 📜 Recent Activities")
    
    # Sample recent activities
    activities = [
        {"time": "10 mins ago", "action": "Production Order PO-20250106-001 created", "user": "John Doe", "type": "info"},
        {"time": "25 mins ago", "action": "Material issued for Kitting order KIT-20250106-003", "user": "Jane Smith", "type": "success"},
        {"time": "1 hour ago", "action": "BOM updated for Product ABC-123", "user": "Admin", "type": "warning"},
        {"time": "2 hours ago", "action": "5 units received from production order PO-20250106-002", "user": "Mike Wilson", "type": "success"},
    ]
    
    for activity in activities:
        col1, col2, col3 = st.columns([1, 6, 2])
        with col1:
            st.markdown(f"🕒 {activity['time']}")
        with col2:
            if activity['type'] == 'success':
                st.success(activity['action'])
            elif activity['type'] == 'warning':
                st.warning(activity['action'])
            else:
                st.info(activity['action'])
        with col3:
            st.markdown(f"👤 {activity['user']}")
    
    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #888;'>
        Manufacturing Module v1.0 | Part of iSCM System | © 2025 ProsTech
        </div>
        """,
        unsafe_allow_html=True
    )