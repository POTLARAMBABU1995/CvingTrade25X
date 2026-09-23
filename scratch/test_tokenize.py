import tokenize

with open("backend/services/marketdata_service.py", "rb") as f:
    gen = tokenize.tokenize(f.readline)
    while True:
        try:
            tok = next(gen)
            if 1885 <= tok.start[0] <= 1910:
                print(f"Tok {tok.start} to {tok.end}: {tokenize.tok_name[tok.type]} - {repr(tok.string)}")
        except StopIteration:
            break
        except tokenize.TokenError as exc:
            print(f"TokenError: {exc}")
            break
