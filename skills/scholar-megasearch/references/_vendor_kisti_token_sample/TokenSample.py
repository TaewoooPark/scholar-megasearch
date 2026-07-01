import requests
import traceback
import AES256Util
import datetime
import re
import json


################################################### 사용자 정보 입력 #####################################################
# 맥주소 입력하세요.
MAC_address = ""
# 발급받은 client_id를 입력하세요.
clientID = ""
# 발급받은 인증키를 입력해주세요.
key = ""
#######################################################################################################################
time = ''.join(re.findall("\d", datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
plain_txt = json.dumps({"datetime": time, "mac_address": MAC_address}).replace(" ", "")
refreshToken = ""
accessToken = ""


# Access Token 및 Refresh Token 발급
def generateToken():
    encryption = AES256Util.AESTestClass(plain_txt, key)
    encrypted_txt = encryption.encrypt()
    target_URL = "https://apigateway.kisti.re.kr/tokenrequest.do?client_id=" + clientID + "&accounts=" + encrypted_txt

    try:
        response = requests.get(target_URL)
        # API 호출 결과값 출력
        print(response.text)

        # 발급된 토큰(Refresh Token, Access Token) global 변수 입력
        json_object = json.loads(response.text)
        global refreshToken, accessToken
        refreshToken = json_object['refresh_token']
        accessToken = json_object['access_token']
        print(refreshToken)
        print(accessToken)

    except Exception:
        traceback.print_exc()

# Access Token 재발급
def regenerateToken():
    target_URL = "https://apigateway.kisti.re.kr/tokenrequest.do?refreshToken=" + refreshToken + "&client_id=" + clientID

    try:
        response = requests.get(target_URL)
        # API 호출 결과값 출력
        print(response.text)

        # 발급된 토큰(Access Token) 변수 입력
        json_object = json.loads(response.text)
        global accessToken
        accessToken = json_object['access_token']
        print(accessToken)

    except Exception:
        traceback.print_exc()


# 함수 호출
generateToken()

