import tokenize

def trace_strings_iterative(filepath):
    with open(filepath, 'rb') as f:
        gen = tokenize.tokenize(f.readline)
        while True:
            try:
                tok = next(gen)
                if tok.type == tokenize.STRING:
                    # Print line and content snippet
                    snippet = tok.string.replace('\n', ' ')
                    if len(snippet) > 60:
                        snippet = snippet[:60] + '...'
                    print(f"Line {tok.start[0]}: {snippet}")
            except StopIteration:
                break
            except tokenize.TokenError as exc:
                print(f"TokenError: {exc.args[0]} at {exc.args[1]}")
                break

trace_strings_iterative(r"c:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\backend\services\marketdata_service.py")
