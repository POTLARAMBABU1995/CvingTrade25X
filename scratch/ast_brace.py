import tokenize

def check_tokens(filepath):
    try:
        with open(filepath, 'rb') as f:
            tokens = list(tokenize.tokenize(f.readline))
        print("Tokenization succeeded!")
    except tokenize.TokenError as exc:
        print(f"TokenError: {exc.args[0]}")
        print(f"Location: {exc.args[1]}")

check_tokens(r"c:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\backend\services\marketdata_service.py")
