# Deployment Plan: AC Schnitzer Scraper & Updater

This deployment plan is tailored specifically for the AC Schnitzer project. It leverages the existing `run_updates.py` orchestration script to provide a robust, automated solution for keeping product data in sync.

## Strategy

We will deploy a single **Docker container** that encapsulates the Python environment and dependencies. This ensures consistency across development and production.

The system can run in two modes (configurable via `docker-compose.yml`):
1.  **Headless Scheduler (Default)**: A background process that runs `run_updates.py` automatically every day.
2.  **Interactive Dashboard (Optional)**: A lightweight Streamlit web UI to manually trigger updates, view logs, and download the generated CSVs.

## 1. Project Structure

Prepare your local directory to look like this before deploying.

```text
ac_schnitzer/
├── src/
│   ├── convert_products_to_csv.py
│   ├── run_updates.py
│   ├── scrape_links.py
│   ├── scrape_products.py
│   ├── update_lastmod.py
│   ├── scheduler.py
│   └── app.py
├── data/
│   ├── product_details.json         # Persisted DB
│   └── product_links.json           # Persisted Cache
├── output/
│   └── woocommerce_products.csv     # Generated CSVs
├── docs/
│   ├── deployment_plan.md
│   └── documentation.md
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## 2. Required Files

### `requirements.txt`
Includes all libraries used by your scripts plus `schedule` and `streamlit` for the deployment layer.

```text
requests
beautifulsoup4
lxml
rich
pandas
schedule
streamlit
watchdog
```

### `Dockerfile`
Defines the environment. We use a slim Python 3.10 image to keep it lightweight.

```dockerfile
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies (needed for lxml and some network tools)
RUN apt-get update && apt-get install -y \
    gcc \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all scripts
COPY . .

# Create a directory for outputs if it doesn't exist
RUN mkdir -p output

# Expose the Streamlit port (optional, but good to have ready)
EXPOSE 8501

# Default command (can be overridden in docker-compose)
CMD ["python", "src/scheduler.py"]
```

### `src/scheduler.py`
A simple script to run your `run_updates.py` on a schedule.

```python
import schedule
import time
import run_updates
import sys
import logging

# Configure logging to stdout
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(asctime)s - %(message)s')

def job():
    logging.info("Starting scheduled daily update...")
    try:
        # Call the main function of your existing script
        run_updates.main()
        logging.info("Daily update finished successfully.")
    except Exception as e:
        logging.error(f"Daily update failed: {e}")

# Schedule the job every day at 08:00
schedule.every().day.at("08:00").do(job)

if __name__ == "__main__":
    logging.info("Scheduler started. Waiting for next job...")
    while True:
        schedule.run_pending()
        time.sleep(60)
```

### `src/app.py` (Optional UI)
A Streamlit dashboard that wraps your existing scripts.

```python
import streamlit as st
import run_updates
import sys
import os
import pandas as pd
from io import StringIO
import contextlib

st.set_page_config(page_title="AC Schnitzer Scraper", layout="wide")

st.title("AC Schnitzer Scraper Dashboard")

st.markdown("""
This dashboard controls the `run_updates.py` workflow.
- **Check for Updates**: Downloads sitemap, finds changes, scrapes new data.
- **Download CSV**: Get the latest WooCommerce import file.
""")

# --- Status Section ---
if os.path.exists("output/woocommerce_products_updated.csv"):
    st.success("Latest Update CSV Available")
    with open("output/woocommerce_products_updated.csv", "rb") as f:
        st.download_button("Download Updated CSV", f, file_name="woocommerce_products_updated.csv")
else:
    st.info("No recent update CSV found.")

# --- Actions ---
if st.button("Run Update Workflow Now"):
    with st.spinner("Running update workflow... This may take a while."):
        # Capture stdout to show logs in UI
        log_capture = StringIO()
        
        try:
            # Redirect stdout to capture logs
            with contextlib.redirect_stdout(log_capture):
                run_updates.main()
            
            st.success("Workflow Completed!")
            st.expander("View Logs").code(log_capture.getvalue())
            
            # Refresh to show download button
            st.rerun()
            
        except Exception as e:
            st.error(f"An error occurred: {e}")
            st.expander("View Error Logs").code(log_capture.getvalue())

# --- Data Preview ---
st.subheader("Data Preview")
if os.path.exists("data/product_details.json"):
    st.write(f"Database size: {os.path.getsize('data/product_details.json') / (1024*1024):.2f} MB")
```

### `docker-compose.yml`
Orchestrates the container and handles file persistence.

```yaml
version: '3.8'

services:
  scraper:
    build: .
    container_name: ac_schnitzer_bot
    restart: unless-stopped
    
    # OPTION 1: Run as a background scheduler (Default)
    # command: python src/scheduler.py
    
    # OPTION 2: Run as a Web UI (Uncomment to use)
    command: streamlit run src/app.py --server.port=8501 --server.address=0.0.0.0
    ports:
      - "8501:8501"
      
    volumes:
      # Persist the critical data files so they survive restarts
      - ./data:/app/data
      # Persist the output CSVs
      - ./output:/app/output
      
    environment:
      - TZ=UTC # Set your desired timezone
```

---

## 3. Deployment Steps (VPS)

1.  **Transfer Files**: Upload the entire project folder to your VPS (e.g., `/opt/ac_schnitzer`).
2.  **Install Docker**: If not already installed.
    ```bash
    curl -fsSL https://get.docker.com | sh
    ```
3.  **Start the Service**:
    ```bash
    cd /opt/ac_schnitzer
    docker compose up -d --build
    ```
4.  **Verify**:
    - Check logs: `docker logs -f ac_schnitzer_bot`
    - If using UI, visit: `http://<YOUR_VPS_IP>:8501`

## 4. Maintenance

-   **Logs**: The container logs all activity. Use `docker logs ac_schnitzer_bot` to see the output of the scraper.
-   **Backups**: Regularly backup `data/product_details.json`. This is your master database.
-   **Updates**: If you modify the Python scripts, just run `docker compose up -d --build` to rebuild the container with the new code.