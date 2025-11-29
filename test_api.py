import requests

url = "http://localhost:5000/download/ac_schnitzer_78142"
try:
    response = requests.get(url)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print("Success: File content received.")
        print(f"Content Start: {response.content[:100]}")
    else:
        print(f"Failed: {response.text}")
except Exception as e:
    print(f"Error: {e}")
