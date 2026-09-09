import requests
import sys

case_id = sys.argv[1]
file_path = r"C:\Users\jaipr\Pramaan\validation_data\external\dvr\dahua\20.49.55-20.50.21_M_0_0_0_.dav"

print(f"Acquiring {file_path} for case {case_id}")

url = f"http://127.0.0.1:8787/api/v1/cases/{case_id}/devices/acquire"
with open(file_path, "rb") as f:
    files = {"file": f}
    data = {"actor": "LiveAuditor"}
    resp = requests.post(url, files=files, data=data)

print(resp.status_code)
print(resp.json())
