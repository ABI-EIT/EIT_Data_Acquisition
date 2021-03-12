from multiprocessing import Process, Pipe, Value
import time
import threading
import atexit

def f(conn, val):
    while val.value != 0:
        conn.send(val.value)
        time.sleep(1)
    print("done")


def wait_on_pipe(con):
    while(1):
        result = con.recv()
        print(result)


def set_zero(value_dict):
    print("setzero")
    value_dict["val"].value = 0


if __name__ == '__main__':
    val = Value('i', 1)
    valdict = {"val":val}
    atexit.register(set_zero, valdict)
    parent_conn, child_conn = Pipe()
    p = Process(target=f, args=(child_conn, val))
    p.start()
    t = threading.Thread(target=wait_on_pipe, args=(parent_conn,), daemon=True)
    t.start()
    time.sleep(7)

