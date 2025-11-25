import streamlit as st
import subprocess
import sys
import os
import re
import time
import zipfile
from pathlib import Path

import base64

# --- Configuration ---
st.set_page_config(
    page_title="Datona | AC Schnitzer Updates",
    page_icon="../public/images/logo_icon.png",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- Constants ---
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"
SCRIPT_PATH = BASE_DIR / "src" / "run_updates.py"
CONVERT_SCRIPT_PATH = BASE_DIR / "src" / "convert_products_to_csv.py"
LOGO_PATH = BASE_DIR / "public" / "images" / "logo_icon.png"
BATCH_ZIP_PREFIX = "woocommerce_batch_export_"

# --- Custom CSS (Datona Brand) ---
def load_css():
    st.markdown("""
        <style>
        /* Main Background */
        .stApp {
            background: linear-gradient(135deg, #1a0b14 0%, #0f050a 100%);
            color: #ffffff;
            font-family: 'Helvetica Neue', sans-serif;
        }

        /* Header Styling */
        .main-header {
            font-size: 3rem;
            font-weight: 800;
            background: -webkit-linear-gradient(45deg, #ff00cc, #333399);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-align: center;
            margin-bottom: 1rem;
            letter-spacing: -1px;
            text-shadow: 0px 0px 30px rgba(255, 0, 204, 0.3);
            padding-right: 0.1em;
            display: inline-block;
        }
        
        .sub-header {
            font-size: 1.2rem;
            color: #b3b3b3;
            text-align: center;
            margin-bottom: 3rem;
            font-weight: 300;
        }

        .header-container {
            margin-bottom: 1rem;
        }

        /* Button Styling */
        .stButton > button {
            background: linear-gradient(90deg, #b30086 0%, #800060 100%);
            color: white;
            border: none;
            padding: 0.75rem 2rem;
            font-size: 1.2rem;
            font-weight: 600;
            border-radius: 50px;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(179, 0, 134, 0.4);
            width: 100%;
        }

        .stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(179, 0, 134, 0.6);
            background: linear-gradient(90deg, #d4009f 0%, #a6007c 100%);
        }

        .stButton > button:active {
            transform: translateY(1px);
        }

        /* Small Button Variant */
        .small-button .stButton > button {
            padding: 0.5rem 1rem;
            font-size: 0.9rem;
            font-weight: 500;
        }

        /* Download Button Specifics */
        .stDownloadButton > button {
            background: linear-gradient(90deg, #b30086 0%, #800060 100%);
            color: white !important;
            border: none;
            padding: 0.75rem 2rem;
            font-size: 1.2rem;
            font-weight: 600;
            border-radius: 50px;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(179, 0, 134, 0.4);
            width: 100%;
        }
        .stDownloadButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(179, 0, 134, 0.6);
            background: linear-gradient(90deg, #d4009f 0%, #a6007c 100%);
            color: white !important;
        }

        /* Console Output Area */
        .console-output {
            background-color: #0a0a0a;
            border: 1px solid #333;
            border-radius: 10px;
            padding: 1rem;
            font-family: 'Courier New', monospace;
            font-size: 0.9rem;
            color: #00ff99;
            height: 400px;
            overflow-y: auto;
            box-shadow: inset 0 0 20px rgba(0,0,0,0.8);
        }

        /* File Download Section */
        .file-card {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 15px;
            padding: 1.5rem;
            margin-bottom: 1rem;
            transition: all 0.3s ease;
        }

        .file-card:hover {
            background: rgba(255, 255, 255, 0.08);
            border-color: #b30086;
        }

        /* Scrollbar */
        ::-webkit-scrollbar {
            width: 10px;
            height: 10px;
        }
        ::-webkit-scrollbar-track {
            background: #0f050a; 
        }
        ::-webkit-scrollbar-thumb {
            background: #333; 
            border-radius: 5px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: #b30086; 
        }
        
        /* Expander */
        .streamlit-expanderHeader {
            background-color: rgba(255,255,255,0.05);
            border-radius: 10px;
        }

        /* Section Headers */
        .section-header {
            font-size: 1.5rem;
            font-weight: 700;
            background: -webkit-linear-gradient(45deg, #ff00cc, #333399);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: rem;
            text-shadow: 0px 0px 15px rgba(255, 0, 204, 0.2);
        }

        /* Responsive adjustments */
        @media (max-width: 768px) {
            .main-header {
                font-size: 2rem;
            }
            .header-container {
                margin-bottom: 0.1rem !important;
            }
            img[alt="Logo"] {
                height: 2.5rem !important;
                margin-right: 0.5rem !important;
                margin-top: -1.0rem !important;
            }
            .sub-header {
                margin-bottom: 3rem !important;
            }
        }
        </style>
    """, unsafe_allow_html=True)

# --- Helper Functions ---
def strip_ansi(text):
    """Strips ANSI escape codes from text."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def get_logo_base64():
    """Returns the logo image as a base64 encoded string."""
    try:
        with open(LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        return None

def run_update_script():
    """Runs the update script and yields output lines."""
    cmd = [sys.executable, str(SCRIPT_PATH)]
    
    # Use subprocess.Popen to run the script
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding='utf-8',
        cwd=str(BASE_DIR) # Run from base dir so relative paths work
    )
    
    return process


def run_batch_convert(batch_size: int, price_formula: str = ""):
    """Runs the batch conversion script with specified batch size and optional price formula."""
    cmd = [
        sys.executable,
        str(CONVERT_SCRIPT_PATH),
        "--input", str(DATA_DIR / "product_details.json"),
        "--output", str(OUTPUT_DIR / "woocommerce_products.csv"),
        "--batch", str(batch_size)
    ]
    
    if price_formula:
        cmd.extend(["--price-formula", price_formula])
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding='utf-8',
        cwd=str(BASE_DIR)
    )
    
    return process


def cleanup_batch_files():
    """Removes old batch CSV files and ZIP archives from output directory."""
    if not OUTPUT_DIR.exists():
        return
    
    # Remove batch CSV files (woocommerce_products_1.csv, _2.csv, etc.)
    for f in OUTPUT_DIR.glob("woocommerce_products_*.csv"):
        # Skip the main files
        if f.name in ("woocommerce_products.csv", "woocommerce_products_updated.csv"):
            continue
        f.unlink()
    
    # Remove existing ZIP archives
    for f in OUTPUT_DIR.glob(f"{BATCH_ZIP_PREFIX}*.zip"):
        f.unlink()


def create_batch_zip() -> bool:
    """Creates a ZIP archive from batch CSV files and removes the individual CSVs."""
    if not OUTPUT_DIR.exists():
        return False
    
    # Find all batch CSV files
    batch_files = sorted([
        f for f in OUTPUT_DIR.glob("woocommerce_products_*.csv")
        if f.name not in ("woocommerce_products.csv", "woocommerce_products_updated.csv")
    ])
    
    if not batch_files:
        return False
    
    # Create unique ZIP name with timestamp
    timestamp = int(time.time())
    zip_name = f"{BATCH_ZIP_PREFIX}{timestamp}.zip"
    zip_path = OUTPUT_DIR / zip_name
    
    # Create ZIP archive
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for csv_file in batch_files:
            zf.write(csv_file, csv_file.name)
    
    # Remove individual batch CSV files after zipping
    for csv_file in batch_files:
        csv_file.unlink()
    
    return True

# --- Main UI ---
def main():
    load_css()

    # Get logo as base64
    logo_base64 = get_logo_base64()
    logo_html = f'<img src="data:image/png;base64,{logo_base64}" style="height: 4rem; margin-right: 1rem; margin-top: -1.0rem;" alt="Logo">' if logo_base64 else ''

    # Header
    st.markdown(f'''
        <div class="header-container" style="display: flex; align-items: center; justify-content: center; padding: 0 2rem;">
            {logo_html}
            <div class="main-header">DATONA</div>
        </div>
    ''', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">AC Schnitzer Product Scraping Hub</div>', unsafe_allow_html=True)

    # Layout - Top Section (Actions & Downloads)
    top_col1, top_col2 = st.columns([2, 1], gap="large")

    with top_col1:
        # Actions section
        st.markdown('<div class="section-header">Actions</div>', unsafe_allow_html=True)
        
        # Check if any process is running
        is_running = st.session_state.get("running", False) or st.session_state.get("batch_running", False)
        
        # Row 1: Run Updates
        st.markdown("**Sync Products** — Download the latest sitemap, scrape new products, and generate updated CSV files.")
        with st.container():
            st.markdown('<div class="small-button">', unsafe_allow_html=True)
            if st.button("RUN UPDATES NOW", disabled=is_running, key="update_btn"):
                st.session_state.running = True
                st.session_state.logs = []
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('<div style="margin-bottom: 1rem;"></div>', unsafe_allow_html=True)
        
        # Row 2: Batch Convert
        st.markdown("**Batch Convert** — Convert all products to multiple CSV files and package them into a ZIP archive.")
        
        # Pricing Formula Section
        st.markdown("##### Pricing Configuration")
        
        # Formula Explanation
        st.info("""
        **Formula Variables:**
        *   `x`: Original Price (EUR)
        *   `0.755`: Discount Factor (1 - 0.245) [24.5% Discount]
        *   `12.0231788079`: Conversion Rate (EUR to NOK)
        *   `1.277884880198`: Markup Factor (1 + 0.2778...) [~27.8% Markup]
        """)

        use_formula = st.checkbox("Enable Pricing Formula", value=True, disabled=is_running)
        price_formula = st.text_input(
            "Pricing Formula", 
            value="x * 0.755 * 12.0231788079 * 1.277884880198", 
            disabled=not use_formula or is_running,
            help="Modify the formula as needed. Use 'x' for the original price."
        )
        
        batch_col1, batch_col2 = st.columns([1, 1])
        
        with batch_col1:
            batch_size = st.slider(
                "Batch Size (rows per file)",
                min_value=50,
                max_value=200,
                value=100,
                step=10,
                disabled=is_running,
                key="batch_size_slider"
            )
            # Update session state for batch size immediately if needed, but slider does it automatically via key
            st.session_state.batch_size_input = batch_size
            
            if st.button("RUN BATCH CONVERT", disabled=is_running, key="batch_btn"):
                st.session_state.batch_running = True
                st.session_state.batch_size = st.session_state.get("batch_size_input", 100) # Use session state or default
                # Store formula in session state only if enabled
                st.session_state.price_formula = price_formula if use_formula else ""
                st.session_state.logs = []
                st.rerun()

        with batch_col2:
            pass

    with top_col2:
        st.markdown('<div style="display: flex; flex-direction: column; align-items: center;">', unsafe_allow_html=True)
        st.markdown('<div class="section-header">Downloads</div>', unsafe_allow_html=True)
        st.markdown("Download the generated CSV files.")
        
        # Initialize session state for download button tracking
        if "download_session_id" not in st.session_state:
            import random
            st.session_state.download_session_id = random.randint(100000, 999999)
        
        # Mapping for display names
        display_names = {
            "woocommerce_products.csv": "All Products",
            "woocommerce_products_updated.csv": "Updates Only"
        }
        
        # List files in output directory
        if OUTPUT_DIR.exists():
            files = [f for f in OUTPUT_DIR.glob("*") if f.is_file() and (f.suffix == ".csv" or f.suffix == ".zip")]
            # Filter out temp batch files if any remain (though cleanup handles them)
            files = [f for f in files if not (f.name.startswith("woocommerce_products_") and f.name not in ["woocommerce_products_updated.csv"] and f.suffix == ".csv")]

            if not files:
                st.info("No files found in output directory.")
            else:
                # Sort files: All Products first, then Updates Only, then ZIP
                def sort_key(x):
                    if x.name == "woocommerce_products.csv":
                        return 0
                    elif x.name == "woocommerce_products_updated.csv":
                        return 1
                    elif x.name.startswith(BATCH_ZIP_PREFIX):
                        return 2
                    else:
                        return 3
                
                files.sort(key=sort_key)
                
                for idx, file_path in enumerate(files):
                    if file_path.name.startswith(BATCH_ZIP_PREFIX):
                        display_name = "Batch Export (ZIP)"
                    else:
                        display_name = display_names.get(file_path.name, file_path.name)
                    with open(file_path, "rb") as f:
                        file_data = f.read()
                        file_size_kb = file_path.stat().st_size / 1024
                        size_str = f"{file_size_kb / 1024:.1f} MB" if file_size_kb >= 1024 else f"{file_size_kb:.1f} KB"
                        
                        # Determine icon and MIME type
                        if file_path.suffix == ".zip":
                            icon = "📦"
                            mime_type = "application/zip"
                        elif file_path.suffix == ".csv":
                            icon = "📄"
                            mime_type = "text/csv"
                        else:
                            icon = "📁"
                            mime_type = "application/octet-stream"
                        
                        # For ZIP files, add a delete button next to the download button
                        if file_path.suffix == ".zip":
                            dl_col, del_col = st.columns([5, 1])
                            with dl_col:
                                st.download_button(
                                    label=f"{icon} {display_name} ({size_str})",
                                    data=file_data,
                                    file_name=file_path.name,
                                    mime=mime_type,
                                    key=f"download_{st.session_state.download_session_id}_{idx}_{file_path.name}"
                                )
                            with del_col:
                                if st.button("🗑️", key=f"delete_{st.session_state.download_session_id}_{idx}_{file_path.name}"):
                                    file_path.unlink()  # Delete the file
                                    st.rerun()  # Refresh the page
                        else:
                            st.download_button(
                                label=f"{icon} {display_name} ({size_str})",
                                data=file_data,
                                file_name=file_path.name,
                                mime=mime_type,
                                key=f"download_{st.session_state.download_session_id}_{idx}_{file_path.name}"
                            )
        else:
            st.error(f"Output directory not found: {OUTPUT_DIR}")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div style="margin-bottom: 2rem;"></div>', unsafe_allow_html=True)

    # Console Output Section (Full Width)
    st.markdown('<div class="section-header">Console Output</div>', unsafe_allow_html=True)
    
    log_container = st.empty()
    
    # Initialize logs in session state if not present
    if "logs" not in st.session_state:
        st.session_state.logs = []

    # Display existing logs
    log_text = "\n".join(st.session_state.logs)
    if log_text:
        log_container.code(log_text, language="bash")
    else:
        log_container.info("Ready to run. Logs will appear here.")

    # Run script logic
    if st.session_state.get("running", False):
        process = run_update_script()
        
        # Stream output
        for line in iter(process.stdout.readline, ''):
            clean_line = strip_ansi(line).rstrip()
            if clean_line:
                st.session_state.logs.append(clean_line)
                # Update the code block with new logs
                # We keep the last 1000 lines to avoid performance issues if it gets huge
                if len(st.session_state.logs) > 1000:
                    st.session_state.logs = st.session_state.logs[-1000:]
                
                log_text = "\n".join(st.session_state.logs)
                log_container.code(log_text, language="bash")
        
        process.stdout.close()
        return_code = process.wait()
        
        if return_code == 0:
            st.success("Update completed successfully!")
            st.balloons()
        else:
            st.error("Update failed. Check logs for details.")
        
        st.session_state.running = False
        # Rerun to update file list
        st.rerun()
    
    # Run batch convert logic
    if st.session_state.get("batch_running", False):
        batch_size = st.session_state.get("batch_size", 100)
        
        # Cleanup old batch files and archives
        st.session_state.logs.append("Cleaning up old batch files...")
        log_container.code("\n".join(st.session_state.logs), language="bash")
        cleanup_batch_files()
        
        st.session_state.logs.append(f"Starting batch conversion with batch size: {batch_size}")
        if st.session_state.get("price_formula"):
            st.session_state.logs.append(f"Applying pricing formula: {st.session_state.price_formula}")
        log_container.code("\n".join(st.session_state.logs), language="bash")
        
        process = run_batch_convert(batch_size, st.session_state.get("price_formula", ""))
        
        # Stream output
        for line in iter(process.stdout.readline, ''):
            clean_line = strip_ansi(line).rstrip()
            if clean_line:
                st.session_state.logs.append(clean_line)
                if len(st.session_state.logs) > 1000:
                    st.session_state.logs = st.session_state.logs[-1000:]
                
                log_text = "\n".join(st.session_state.logs)
                log_container.code(log_text, language="bash")
        
        process.stdout.close()
        return_code = process.wait()
        
        if return_code == 0:
            # Create ZIP archive
            st.session_state.logs.append("Creating ZIP archive...")
            log_container.code("\n".join(st.session_state.logs), language="bash")
            
            if create_batch_zip():
                st.session_state.logs.append(f"ZIP archive created.")
                log_container.code("\n".join(st.session_state.logs), language="bash")
                st.success("Batch conversion completed successfully!")
                st.balloons()
            else:
                st.warning("Batch conversion completed but no files were generated.")
        else:
            st.error("Batch conversion failed. Check logs for details.")
        
        st.session_state.batch_running = False
        st.rerun()

if __name__ == "__main__":
    main()
