from Crypto.Cipher import AES
from urllib.parse import quote
import base64


class AESTestClass:
    def __init__(self, plain_txt, key):
        # iv, block_size 값은 고정입니다.
        self.iv = 'jvHJ1EFA0IXBrxxz'
        self.block_size = 16
        self.plain_txt = plain_txt
        self.key = key

    def pad(self):
        number_of_bytes_to_pad = self.block_size - len(self.plain_txt) % self.block_size
        ascii_str = chr(number_of_bytes_to_pad)
        padding_str = number_of_bytes_to_pad * ascii_str
        padded_plain_text = self.plain_txt + padding_str
        return padded_plain_text

    def encrypt(self):
        cipher = AES.new(self.key.encode('utf-8'), AES.MODE_CBC, self.iv.encode('utf-8'))
        padded_txt = AESTestClass.pad(self)
        encrypted_bytes = cipher.encrypt(padded_txt.encode('utf-8'))
        encrypted_str = base64.urlsafe_b64encode(encrypted_bytes).decode("utf-8")
        encrypted_encoded = quote(encrypted_str)
        return encrypted_encoded
