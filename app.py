import asyncio
import aiohttp
from flask import Flask, request, jsonify
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import binascii
from secret import *
import uid_generator_pb2
import time
from datetime import datetime
import random

app = Flask(__name__)

# تخزين المفاتيح هنا
api_keys = set()

last_like_time = {}

def create_protobuf(saturn_, garena):
    message = uid_generator_pb2.uid_generator()
    message.saturn_ = saturn_
    message.garena = garena
    return message.SerializeToString()

def protobuf_to_hex(protobuf_data):
    return binascii.hexlify(protobuf_data).decode()

def encrypt_aes(hex_data, key, iv):
    key = key.encode()[:16]
    iv = iv.encode()[:16]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded_data = pad(bytes.fromhex(hex_data), AES.block_size)
    encrypted_data = cipher.encrypt(padded_data)
    return binascii.hexlify(encrypted_data).decode()

# إدارة المفاتيح
@app.route('/make_key', methods=['GET'])
def make_key():
    key = request.args.get('key')
    if not key:
        return jsonify({'error': 'Missing key parameter'}), 400
    api_keys.add(key)  # إضافة المفتاح للمجموعة
    return jsonify({'message': 'Key added successfully', 'key': key}), 200

@app.route('/del_key', methods=['GET'])
def del_key():
    key = request.args.get('key')
    if not key:
        return jsonify({'error': 'Missing key parameter'}), 400
    if key in api_keys:
        api_keys.remove(key)
        return jsonify({'message': 'Key deleted successfully', 'key': key}), 200
    else:
        return jsonify({'error': 'Key not found'}), 404

@app.route('/del_all_keys', methods=['GET'])
def del_all_keys():
    api_keys.clear()
    return jsonify({'message': 'All keys deleted successfully'}), 200

@app.route('/all_keys', methods=['GET'])
def all_keys():
    return jsonify({'keys': list(api_keys)}), 200

# التحقق من صحة المفتاح
def verify_key(key):
    return key in api_keys

# دالة الإعجاب
async def like(id, session, token):
    like_url = 'https://clientbp.ggblueshark.com/LikeProfile'
    headers = {
        'X-Unity-Version': '2018.4.11f1',
        'ReleaseVersion': 'OB48',
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-GA': 'v1 1',
        'Authorization': f'Bearer {token}',
        'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 7.1.2; ASUS_Z01QD Build/QKQ1.290125.002)',
        'Host': 'clientbp.ggblueshark.com',
        'Connection': 'Keep-Alive',
        'Accept-Encoding': 'gzip'
    }

    data = bytes.fromhex(id)

    async with session.post(like_url, headers=headers, data=data) as response:
        status_code = response.status
        response_text = await response.text()
        return {
            'status_code': status_code,
            'response_text': response_text
        }

async def get_account_info(uid, session):
    info_url = f'http://127.0.0.1:5002/{uid}'
    async with session.get(info_url) as response:
        if response.status == 200:
            return await response.json()
        else:
            return None

async def get_tokens(session):
    url = 'https://sktokenss.vercel.app/token'
    async with session.get(url) as response:
        if response.status == 200:
            tokens = await response.json()  # تحويل النتيجة إلى JSON
            token_list = tokens.get('tokens', [])  # الحصول على قائمة tokens
            return token_list[:215]  # إرجاع أول 99 توكن فقط
        else:
            return []  # إرجاع قائمة فارغة في حالة فشل الطلب

async def sendlike(uid, count=1):
    saturn_ = int(uid)
    garena = 1
    protobuf_data = create_protobuf(saturn_, garena)
    hex_data = protobuf_to_hex(protobuf_data)
    aes_key = key
    aes_iv = iv
    id = encrypt_aes(hex_data, aes_key, aes_iv)

    start_time = time.time()  # بداية المراقبة للوقت

    # تحقق مما إذا كانت قد مرّت 24 ساعة على آخر لايك
    current_time = datetime.now()
    last_time = last_like_time.get(uid)

    async with aiohttp.ClientSession() as session:
        tokens = await get_tokens(session)  # الحصول على قائمة tokens (أول 99 توكن)

        if not tokens:
            return jsonify({"error": "No tokens available"}), 500

        # جلب معلومات الحساب قبل إضافة الإعجابات
        account_info_before = await get_account_info(uid, session)
        if not account_info_before:
            return jsonify({"error": "Unable to fetch account info before sending likes"}), 500

        likes_before = account_info_before['basicinfo'][0]['likes']  # الإعجابات قبل

        # إرسال الإعجابات
        tasks = [like(id, session, token) for token in tokens[:count]]  # إرسال عدد محدد من الإعجابات
        results = await asyncio.gather(*tasks)

        # جلب معلومات الحساب بعد إضافة الإعجابات
        account_info_after = await get_account_info(uid, session)
        if not account_info_after:
            return jsonify({"error": "Unable to fetch account info after sending likes"}), 500

        likes_after = account_info_after['basicinfo'][0]['likes']  # الإعجابات بعد

        # حساب الإعجابات المضافة فعلياً
        likes_added = likes_after - likes_before
        failed_likes = sum(1 for result in results if result['status_code'] != 200)  # عدد الإعجابات التي فشلت

        end_time = time.time()  # نهاية المراقبة للوقت
        elapsed_time = end_time - start_time 
        
        last_like_time[uid] = current_time

        return jsonify({
            'uid': uid,
            'name': account_info_after['basicinfo'][0].get('username', 'Unknown'),
            'level': account_info_after['basicinfo'][0].get('level', 'N/A'),
            'likes_before': likes_before,
            'likes_after': likes_after,
            'likes_added': likes_added,
            'failed_likes': failed_likes,
            'region': account_info_after['basicinfo'][0].get('region', 'Unknown')
        }), 200

@app.route('/like', methods=['GET'])
def like_endpoint():
    try:
        uid = request.args.get('uid')
        api_key = request.args.get('key')
        count = int(request.args.get('count', 100))  # عدد الإعجابات، الافتراضي 1
        if not uid or not api_key:
            return jsonify({'error': 'Missing uid or key parameter'}), 400

        # التحقق من صحة المفتاح
        if not verify_key(api_key):
            return jsonify({'error': 'Invalid API key'}), 403

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(sendlike(uid, count))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=false)
