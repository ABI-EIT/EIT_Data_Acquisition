
def count(start, stop):
    print("Start")
    value = start
    while value < stop:
        yield value
        value += 1
    print("Stop")


a = count(0,5)
for i in range(0,7):
    try:
        print(next(a))
    except StopIteration:
        print("Got to the end")
        break
