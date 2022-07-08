import os
import cv2
import json
import shutil
import base64
import requests

# import uvicorn
from typing import Optional, List
from fastapi.responses import FileResponse, HTMLResponse
from fastapi import FastAPI, Query, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware

PORT = 7777
HOST = '127.0.0.1'

app = FastAPI()

# adding cors urls
origins = ["*"]

# add middleware
app.add_middleware(
	CORSMiddleware,
	allow_origins=origins,
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"]
)


def save_file(path, file):
	file_object = file.file
	# create empty file to copy the file_object to
	upload_folder = open(os.path.join(path, file.filename), 'wb+')
	shutil.copyfileobj(file_object, upload_folder)
	upload_folder.close()


def get_image_bytes(filename):
	"""Return image as bytes"""
	with open(filename, 'rb') as image:
		return base64.b64encode(image.read())


def bytes_to_str(bytes_):
	"""Bytes to String"""
	return bytes_.decode("utf-8")


def str_to_bytes(str_):
	"""String to Bytes"""
	return str_.encode()


def read_json(filename):
	"""Read json file"""
	try:
		f = open(filename)
		data = json.load(f)
		f.close()
		return data
	except FileNotFoundError:
		return {}


def to_json(data, filename):
	"""Write data to json file"""
	f = open(filename, 'w')
	json.dump(data, f)
	f.close()


def extract_table(data, table_id):
	result = data.copy()
	result["table"] = {key: result["table"][key] for key in [table_id]}
	return result


def replace_table(data, output_of_box_detection):
	result = data.copy()
	table_id = [key for key in output_of_box_detection["table"]][0]
	result["table"][table_id] = output_of_box_detection["table"][table_id]
	return result


def get_next_id():
	dict_keys = list(DATA.keys())
	if len(dict_keys) == 0:
		return 'u0'
	return f'u{int(dict_keys[len(dict_keys) - 1][1:]) + 1}'


JSON_FILENAME = './data.json'
DATA = read_json(JSON_FILENAME)


@app.get('/', response_class=HTMLResponse)
async def root():
	"""Check server"""
	html_content: str = """
	<body style='padding: 0; margin: 0'>
		<div class='loading-gear' style="width: 100%; height: 100%; display: flex; justify-content: center; align-items: center; background: #3e3b94">
			<img src='https://i.pinimg.com/originals/43/7e/d9/437ed9ab2c4ba0d234f58461d7bdded8.gif'>
		</div>
	</body>
	"""
	return HTMLResponse(content=html_content, status_code=200)


@app.get('/image/{filename}')
async def get_image(filename: str, data_type: str = 'bytes'):
	"""Get image by filename"""
	if data_type == 'bytes':
		return FileResponse(f'./static/images/{filename}', media_type="image/jpeg")
	elif data_type == 'b64':
		return {'image': 'data:image/jpeg;base64,'+bytes_to_str(get_image_bytes(f'./static/images/{filename}'))}
	raise HTTPException(status_code=404, detail="Invalid input")



@app.get('/data/users')
async def get_users():
	"""Get all Data"""
	return DATA


@app.post('/data/users')
async def new_user(files: List[UploadFile] = File(...)):
	"""Create User"""
	UPLOAD_FILE_PATH = './static/images/'
	images = {}
	for file in files:
		upload_filename = file.filename
		save_file(UPLOAD_FILE_PATH, file) # save image

		img = cv2.imread(UPLOAD_FILE_PATH + upload_filename) # read image

		images[f'i{len(images.keys())}'] = {
			'filename': upload_filename,
			'url': f"http://{HOST}:{PORT}/image/{upload_filename}",
			'height': img.shape[0],
			'width': img.shape[1],
		}

	next_user_id = get_next_id()
	next_user_id = 'u1'
	DATA[next_user_id] = {
		'image': images
	}

	# to_json(DATA, JSON_FILENAME) # write to the json file

	return {'user_id': next_user_id}


@app.get('/data/{user_id}')
async def get_user(user_id: str):
	"""Get User Data"""
	if user_id in list(DATA.keys()):
		return DATA[user_id]
	raise HTTPException(status_code=404, detail="No Such user")


@app.get('/data/{user_id}/images')
async def get_images(user_id: str):
	"""Get user images"""
	images_data = {}
	if user_id in list(DATA.keys()):
		image_keys = list(DATA[user_id]['image'].keys())
		for image_key in image_keys:
			filename = DATA[user_id]['image'][image_key]['filename']
			images_data[image_key] = {
				'filename': filename,
				'url': f"http://{HOST}:{PORT}/image/{filename}"
			}
		return images_data
	raise HTTPException(status_code=404, detail="No Such user")


@app.get('/data/{user_id}/{image_id}')
async def get_image(user_id: str, image_id: str):
	"""Get Image Data"""
	if user_id in list(DATA.keys()):
		if image_id in list(DATA[user_id]['image'].keys()):
			return DATA[user_id]['image'][image_id]
		raise HTTPException(status_code=404, detail="No Such Image")
	raise HTTPException(status_code=404, detail="No Such User")


@app.put('/data/{user_id}/{image_id}/tables')
async def update_tables(user_id: str, image_id: str, table: dict):
	"""Update Tables"""
	if user_id in list(DATA.keys()):
		if image_id in list(DATA[user_id]['image'].keys()):
			DATA[user_id]['image'][image_id]['table'] = table
			return {'status': 'updated'}
		raise HTTPException(status_code=404, detail="No Such Image")
	raise HTTPException(status_code=404, detail="No Such User")


@app.post('/data/{user_id}/{image_id}/tables')
async def detect_tables(user_id: str, image_id: str):
	"""Update Tables"""
	if user_id in list(DATA.keys()):
		if image_id in list(DATA[user_id]['image'].keys()):
			table_detection_host = 'http://d003-35-186-161-157.ngrok.io'
			url = table_detection_host + '/data/tables/'
			
			_filename = DATA[user_id]['image'][image_id]['filename']
			
			image_bytes = get_image_bytes(f"./static/images/{_filename}")  # image as bytes
			decoded_image_bytes = bytes_to_str(image_bytes)  # byte to str
			request_obj = {'filename': _filename, 'b64_image': decoded_image_bytes}
			print(f'[+] Table Detection...')
			print(f'image: {_filename}')
			response = requests.post(url, json=request_obj)

			table = response.json()
			
			DATA[user_id]['image'][image_id]['table'] = table
			# print('[-] DATA After Table Detection')
			# print(json.dumps(DATA, indent=2))
			print(table)
			return {'data': table}
		raise HTTPException(status_code=404, detail="No Such Image")
	raise HTTPException(status_code=404, detail="No Such User")


@app.get('/data/{user_id}/{image_id}/{table_id}/boxes')
async def get_boxes(user_id: str, image_id: str, table_id: str):
	"""Get Tables"""
	if user_id in list(DATA.keys()):
		if image_id in list(DATA[user_id]['image'].keys()):
			if table_id in list(DATA[user_id]['image'][image_id]['table'].keys()):
				return DATA[user_id]['image'][image_id]['table'][table_id]
			raise HTTPException(status_code=404, detail="No Such Table")
		raise HTTPException(status_code=404, detail="No Such Image")
	raise HTTPException(status_code=404, detail="No Such User")


@app.put('/data/{user_id}/{image_id}/{table_id}/boxes')
async def update_boxes(user_id: str, image_id: str, table_id: str, table: dict):
	"""Update Tables"""
	if user_id in list(DATA.keys()):
		if image_id in list(DATA[user_id]['image'].keys()):
			if table_id in list(DATA[user_id]['image'][image_id]['table'].keys()):
				DATA[user_id]['image'][image_id]['table'][table_id] = table
				return {'status': 'updated'}
			raise HTTPException(status_code=404, detail="No Such Table")
		raise HTTPException(status_code=404, detail="No Such Image")
	raise HTTPException(status_code=404, detail="No Such User")


@app.post('/data/{user_id}/{image_id}/{table_id}/boxes')
async def detect_boxes(user_id: str, image_id: str, table_id: str):
	"""Update Tables"""
	if user_id in list(DATA.keys()):
		if image_id in list(DATA[user_id]['image'].keys()):
			if table_id in list(DATA[user_id]['image'][image_id]['table'].keys()):
				box_detection_host = 'http://0800-35-197-58-93.ngrok.io'
				url_box_detection = box_detection_host + '/data/boxes/'
				
				
				_filename = DATA[user_id]['image'][image_id]['filename']
				
				image_bytes = get_image_bytes(f"./static/images/{_filename}")  # image as bytes
				decoded_image_bytes = bytes_to_str(image_bytes)  # byte to str
				
				# --------------- BOX DETECTION ---------------
				table_data = extract_table(DATA[user_id]['image'][image_id], table_id)
				
				request_obj = {'filename': _filename, 'b64_image': decoded_image_bytes, 'data': table_data}
				print(f'[+] Box Detection...')
				print(f'image: {_filename}')
				response = requests.post(url_box_detection, json=request_obj)
				
				table = response.json()
				
				DATA[user_id]['image'][image_id] = replace_table(DATA[user_id]['image'][image_id], table)
				
				return {
					'table': DATA[user_id]['image'][image_id]['table'][table_id]
				}
			raise HTTPException(status_code=404, detail="No Such Table")
		raise HTTPException(status_code=404, detail="No Such Image")
	raise HTTPException(status_code=404, detail="No Such User")


@app.post('/data/{user_id}/{image_id}/{table_id}/boxes/ocr')
async def optical_recognition(user_id: str, image_id: str, table_id: str):
	"""Update Tables"""
	if user_id in list(DATA.keys()):
		if image_id in list(DATA[user_id]['image'].keys()):
			if table_id in list(DATA[user_id]['image'][image_id]['table'].keys()):
				ocr_host = 'http://fa7a-34-126-189-201.ngrok.io'
				url_ocr = ocr_host + '/data/ocr/'
				
				_filename = DATA[user_id]['image'][image_id]['filename']
				
				image_bytes = get_image_bytes(f"./static/images/{_filename}")  # image as bytes
				decoded_image_bytes = bytes_to_str(image_bytes)  # byte to str
				
				# -------------------- OCR --------------------
				table_data = extract_table(DATA[user_id]['image'][image_id], table_id)

				request_obj = {'filename': _filename, 'b64_image': decoded_image_bytes, 'data': table_data}
				print(f'[+] OCR...')
				print(f"image: {_filename}")
				response = requests.post(url_ocr, json=request_obj)

				table = response.json()

				DATA[user_id]['image'][image_id] = replace_table(DATA[user_id]['image'][image_id], table)
				
				return {
					'table': DATA[user_id]['image'][image_id]['table'][table_id]
				}
			raise HTTPException(status_code=404, detail="No Such Table")
		raise HTTPException(status_code=404, detail="No Such Image")
	raise HTTPException(status_code=404, detail="No Such User")


# if __name__ == '__main__':
# 	uvicorn.run('main:app', host=HOST, port=PORT, reload=True)
