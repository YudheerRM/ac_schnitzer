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
    
    # Run once on startup if needed (uncomment to test immediately)
    # job()
    
    while True:
        schedule.run_pending()
        time.sleep(60)
