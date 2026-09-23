from flask import Flask, request
from routes.sector_rotation import api_sectors_breadth

app = Flask(__name__)
with app.test_request_context('/api/sectors/breadth'):
    try:
        response = api_sectors_breadth()
        print(response)
    except Exception as e:
        import traceback
        traceback.print_exc()
