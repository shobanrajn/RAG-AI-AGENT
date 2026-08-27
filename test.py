import requests
import json

#url = "https://stageconversationalagent.cholamandalam.com/v1/agent" 
# {
#   "user_request": "My Loans",
#   "query_input": "stupid",
#   "session_id": "9182959978_2025072509125123",
#   "mobile_no": "9962410605",
#   "show_more_req_flag": "0",
#   "query_no": "0",
#   "user_text_flag": "1",
#   "otp_verified": "1"
# }

url = "http://127.0.0.1:8000/v1/connector"

headers = {
  'Content-Type': 'application/json',
  'Authorization': 'Basic MWY4NDM4OGIxZjViZWVmMmJjMjE1YzkyOGYxOWY1YjMxNzc4NzAzYWMzOGY4YjMwZDIxZGEwMGJmZjZmMmZmYTpjZTUzOTdiZDY1MWYxOGY0M2ZkMzZiZGNlMWFiYzQwNTgyNDQ1MjVhMDg0MjA2ZGI1YTg1NGI2Mjk3NWUwZWM4'
}

payload = json.dumps({"message": "show payout greater than 3000", "vendor": "9876543210"})

response = requests.request("POST", url, headers=headers, data=payload)
print(response.text)
input("enter")

url = "http://127.0.0.1:8000/v1/agent"

headers = {
  'Content-Type': 'application/json',
  'Authorization': 'Basic MWY4NDM4OGIxZjViZWVmMmJjMjE1YzkyOGYxOWY1YjMxNzc4NzAzYWMzOGY4YjMwZDIxZGEwMGJmZjZmMmZmYTpjZTUzOTdiZDY1MWYxOGY0M2ZkMzZiZGNlMWFiYzQwNTgyNDQ1MjVhMDg0MjA2ZGI1YTg1NGI2Mjk3NWUwZWM4'
}

session_id = "9182959978_2025072509125123"

query_input =  'hi'

payload = json.dumps({'user_request':'', 
                      'query_input': query_input, 
                      'session_id': session_id, 
                      'mobile_no': '9182089282', 
                      'show_more_req_flag': '0', 
                      'query_no': '0', 
                      'user_text_flag': '1', 
                      'otp_verified': '0'})


response = requests.request("POST", url, headers=headers, data=payload)
print(response.text)
input("enter")


query_input = "products of chola"

payload = json.dumps({
    'user_request':'About Chola', 
    'query_input': query_input, 
    'session_id': session_id, 
    'mobile_no': '9597689557', 
    'show_more_req_flag': '0', 
    'query_no': '0', 
    'user_text_flag': '1',
    'otp_verified': '1'})


response = requests.request("POST", url, headers=headers, data=payload)
print(response.text)

input("enter")


query_input =  'show my loan details'

payload = json.dumps({'user_request':'My Loans', 
                      'query_input': query_input, 
                      'session_id': session_id, 
                      'mobile_no': '9553315133', 
                      'show_more_req_flag': '0', 
                      'query_no': '0', 
                      'user_text_flag': '1', 
                      'otp_verified': '1'})

response = requests.request("POST", url, headers=headers, data=payload)
print(response.text)
input("enter")



query_input =  'download welcome letter'

payload = json.dumps({'user_request':'My Loans', 
                      'query_input': query_input, 
                      'session_id': session_id, 
                      'mobile_no': '9553315133', 
                      'show_more_req_flag': '0', 
                      'query_no': '0', 
                      'user_text_flag': '1', 
                      'otp_verified': '1'})

response = requests.request("POST", url, headers=headers, data=payload)
print(response.text)

query_input =  'need mini statement'

payload = json.dumps({
    'user_request':'My Loans', 
    'query_input': query_input, 
    'session_id': session_id, 
    'mobile_no': '9553315133', 
    'show_more_req_flag': '0', 
    'query_no': '0', 
    'user_text_flag': '1',
    'otp_verified': '1'})

response = requests.request("POST", url, headers=headers, data=payload)
print(response.text)
input("enter")

query_input =  'want to pay emi'

payload = json.dumps({'user_request':'My Loans', 
                      'query_input': query_input, 
                      'session_id': session_id, 
                      'mobile_no': '9553315133', 
                      'show_more_req_flag': '0', 
                      'query_no': '0', 
                      'user_text_flag': '1', 
                      'otp_verified': '1'})

response = requests.request("POST", url, headers=headers, data=payload)
print(response.text)

query_input =  'download payment schedule'

payload = json.dumps({'user_request':'My Loans', 
                      'query_input': query_input, 
                      'session_id': session_id, 
                      'mobile_no': '9553315133', 
                      'show_more_req_flag': '0', 
                      'query_no': '0', 
                      'user_text_flag': '1', 
                      'otp_verified': '1'})

response = requests.request("POST", url, headers=headers, data=payload)
print(response.text)












payload = json.dumps({'user_request':'Apply Loan',
                      'query_input': "{'customer_name':'MS. Manikandan  M','pincode':'625515','product_type': 'vf'}", 
                      'session_id': '9182959978_2025027124715', 
                      'mobile_no': '9750635157', 
                      'show_more_req_flag': '0', 
                      'query_no': '2', 
                      'user_text_flag': '1', 
                      'otp_verified': '1',
                      'lead_capture': '1'})

response = requests.request("POST", url, headers=headers, data=payload)
print("V5 Response : ")
print(response.text)
input("enter")

query_input =  'need car loan'

payload = json.dumps({
    'user_request':'Apply Loan', 
    'query_input': query_input, 
    'session_id': session_id, 
    'mobile_no': '9804058202', 
    'show_more_req_flag': '0', 
    'query_no': '0', 
    'user_text_flag': '1',
    'otp_verified': '0'})


response = requests.request("POST", url, headers=headers, data=payload)
print(response.text)
input("enter")



query_input =  'otp_verify'

payload = json.dumps({'user_request':'My Loans', 
                      'query_input': query_input, 
                      'session_id': "9182959978_2025072509125123", 
                      'mobile_no': '9962410605', 
                      'show_more_req_flag': '0', 
                      'query_no': '0', 
                      'user_text_flag': '1', 
                      "verification_code": "1234", 
                      'otp_verified': '0'})

response = requests.request("POST", url, headers=headers, data=payload)
print("V5 Response : ")
print(response.text)
input("enter")







query_input = "otp_generate"

payload = json.dumps({
          "user_request": "My Loans",
          "query_input": query_input,
          "session_id": "9182959978_2025072509125123",
          "mobile_no": "9962410605",
          "show_more_req_flag": "0",
          "query_no": "0",
          "user_text_flag": "1",
          "otp_verified": "0"
        })


response = requests.request("POST", url, headers=headers, data=payload)
print("V5 Response : ")
print(response.text)
input("enter")





query_input = "give me a brief about the content in knowledge base"

payload = json.dumps({
    'user_request':'About Chola', 
    'query_input': query_input, 
    'session_id': session_id, 
    'mobile_no': '9597689557', 
    'show_more_req_flag': '0', 
    'query_no': '0', 
    'user_text_flag': '1',
    'otp_verified': '1'})


response = requests.request("POST", url, headers=headers, data=payload)
print(response.text)

input("enter")


query_input =  'otp_verify'

payload = json.dumps({'user_request':'My Loans', 
                      'query_input': query_input, 
                      'session_id': "9182959978_2025072509125123", 
                      'mobile_no': '9986600053', 
                      'show_more_req_flag': '0', 
                      'query_no': '0', 
                      'user_text_flag': '1', 
                      "verification_code": "1234", 
                      'otp_verified': '0'})

response = requests.request("POST", url, headers=headers, data=payload)
print("V5 Response : ")
print(response.text)
input("enter")


query_input =  ''

payload = json.dumps({'user_request':'My Loans', 
                      'query_input': query_input, 
                      'session_id': "9182959978_2025072509125123", 
                      'mobile_no': '9986600053', 
                      'show_more_req_flag': '1', 
                      'query_no': '0', 
                      'user_text_flag': '1', 
                      "verification_code": "1234", 
                      'otp_verified': '1'})

response = requests.request("POST", url, headers=headers, data=payload)
print("V5 Response : ")
print(response.text)
input("enter")

query_input =  'need car loan'

payload = json.dumps({
    'user_request':'Apply Loan', 
    'query_input': query_input, 
    'session_id': session_id, 
    'mobile_no': '9804058202', 
    'show_more_req_flag': '0', 
    'query_no': '0', 
    'user_text_flag': '1',
    'otp_verified': '0'})


response = requests.request("POST", url, headers=headers, data=payload)
print(response.text)
input("enter")






query_input =  'otp_verify'

payload = json.dumps({'user_request':'My Loans', 
                      'query_input': query_input, 
                      'session_id': "9182959978_2025072509125123", 
                      'mobile_no': '9597689557', 
                      'show_more_req_flag': '0', 
                      'query_no': '0', 
                      'user_text_flag': '1', 
                      "verification_code": "1222", 
                      'otp_verified': '0'})

response = requests.request("POST", url, headers=headers, data=payload)
print("V5 Response : ")
print(response.text)
input("enter")


payload = json.dumps({
    'user_request':'My Loans', 
    'query_input':  'stupid', 
    'session_id': '9182959978_2025072509125123', 
    'mobile_no': '9303731925', 
    'show_more_req_flag': '0', 
    'query_no': '0', 
    'user_text_flag': '1',
    'otp_verified': '1'})


response = requests.request("POST", url, headers=headers, data=payload)
print(response.text)
input("enter")



query_input =  'need welcome letter'

payload = json.dumps({'user_request':'My Loans', 
                      'query_input': query_input, 
                      'session_id': session_id, 
                      'mobile_no': '9787803089', 
                      'show_more_req_flag': '0', 
                      'query_no': '0', 
                      'user_text_flag': '1', 
                      'otp_verified': '1'})

response = requests.request("POST", url, headers=headers, data=payload)
print(response.text)
input("enter")

payload = json.dumps({'user_request':'Apply Loan',
                      'query_input': "{'customer_name':'MS. Manikandan  M','pincode':'625515','product_type': 'vf'}", 
                      'session_id': '9182959978_2025027124715', 
                      'mobile_no': '9750635157', 
                      'show_more_req_flag': '0', 
                      'query_no': '2', 
                      'user_text_flag': '1', 
                      'otp_verified': '1',
                      'lead_capture': '1'})

response = requests.request("POST", url, headers=headers, data=payload)
print("V5 Response : ")
print(response.text)
input("enter")

query_input =  'need home loan'

payload = json.dumps({
    'user_request':'Apply Loan', 
    'query_input': query_input, 
    'session_id': session_id, 
    'mobile_no': '9804058202', 
    'show_more_req_flag': '0', 
    'query_no': '0', 
    'user_text_flag': '1',
    'otp_verified': '1'})


response = requests.request("POST", url, headers=headers, data=payload)
print(response.text)
input("enter")





query_input = "who is the chairman of chola?"

payload = json.dumps({
    'user_request':'About Chola', 
    'query_input': query_input, 
    'session_id': session_id, 
    'mobile_no': '9804058202', 
    'show_more_req_flag': '0', 
    'query_no': '0', 
    'user_text_flag': '1',
    'otp_verified': '1'})


response = requests.request("POST", url, headers=headers, data=payload)
print(response.text)
input("enter")





query_input =  'need welcome letter'#9876543210'#'#

payload = json.dumps({
    'user_request':'My Loans', 
    'query_input': query_input, 
    'session_id': "9182959978_2025072509125123", 
    'mobile_no': '9303731925', 
    'show_more_req_flag': '0', 
    'query_no': '0', 
    'user_text_flag': '1',
    'otp_verified': '1'})


response = requests.request("POST", url, headers=headers, data=payload)
print(response.text)

input("enter")

query_input =  'need mini statement'

payload = json.dumps({
    'user_request':'My Loans', 
    'query_input': query_input, 
    'session_id': session_id, 
    'mobile_no': '8760191236', 
    'show_more_req_flag': '0', 
    'query_no': '0', 
    'user_text_flag': '1',
    'otp_verified': '1'})

response = requests.request("POST", url, headers=headers, data=payload)
print(response.text)





'''
# query_input =  'loan summary'

# payload = json.dumps({'user_request':'', 'query_input': query_input, 'session_id': session_id, 'mobile_no': '9182089282', 'show_more_req_flag': '0', 'query_no': '0', 'user_text_flag': '1', 'otp_verified': '1'})
# headers = {
#   'Content-Type': 'application/json'
# }

# response = requests.request("POST", url, headers=headers, data=payload)
# print("V5 Response : ")
# print(response.text)

# input("enter")

query_input =  'how many loans do i have'
session_id = "test_1234"
payload = json.dumps({'user_request':'My Loans', 'query_input': query_input, 'session_id': session_id, 'mobile_no': '9182089282', 'show_more_req_flag': '0', 'query_no': '0', 'user_text_flag': '1', 'otp_verified': '1'})
headers = {
  'Content-Type': 'application/json'
}

response = requests.request("POST", url, headers=headers, data=payload)
print("V5 Response : ")
print(response.text)

query_input =  'otp_generate'

payload = json.dumps({'user_request':'My Loans', 'query_input': query_input, 'session_id': session_id, 'mobile_no': '9804058202', 'show_more_req_flag': '0', 'query_no': '0', 'user_text_flag': '1', 'otp_verified': '0'})
headers = {
  'Content-Type': 'application/json'
}

response = requests.request("POST", url, headers=headers, data=payload)
print("V5 Response : ")
print(response.text)

query_input =  'how to top up home loan'

payload = json.dumps({'user_request':'About Chola', 'query_input': query_input, 'session_id': session_id, 'mobile_no': '9804058202', 'show_more_req_flag': '0', 'query_no': '0', 'user_text_flag': '1'})
headers = {
  'Content-Type': 'application/json'
}

response = requests.request("POST", url, headers=headers, data=payload)
print("V5 Response : ")
print(response.text)

query_input =  'show my loan details'

payload = json.dumps({'user_request':'My Loans', 'query_input': query_input, 'session_id': session_id, 'mobile_no': '9804058202', 'show_more_req_flag': '0', 'query_no': '0', 'user_text_flag': '1', 'otp_verified': '1'})
headers = {
  'Content-Type': 'application/json'
}


response = requests.request("POST", url, headers=headers, data=payload)
print("V5 Response : ")
print(response.text)


query_input =  'need welcome letter'

payload = json.dumps({'user_request':'My Loans', 'query_input': query_input, 'session_id': session_id, 'mobile_no': '9750635157', 'show_more_req_flag': '0', 'query_no': '0', 'user_text_flag': '1', 'otp_verified': '1'})
headers = {
  'Content-Type': 'application/json'
}


response = requests.request("POST", url, headers=headers, data=payload)
print("V5 Response : ")
print(response.text)



'''