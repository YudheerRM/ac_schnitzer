import csv
import sys

def main():
    csv_path = "output/woocommerce_products_fixed.csv"
    target_name = "AC Schnitzer light soft shell jacket" # Correct title from JSON
    
    print(f"Checking {csv_path}...")
    
    found = False
    with open(csv_path, "r", encoding="utf-8") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            if target_name.lower() in row.get("Name", "").lower():
                print(f"\n--- Found Product: {row['Name']} ---")
                print("Short Description:")
                print(row.get("Short description", "")[:200])
                print("\nDescription:")
                print(row.get("Description", "")[:500])
                print("-" * 40)
                found = True
                break
    
    if not found:
        print(f"Product '{target_name}' not found in CSV.")

if __name__ == "__main__":
    main()
