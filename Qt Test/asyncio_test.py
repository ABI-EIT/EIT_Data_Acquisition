import sys
from PyQt5 import QtWidgets
import asyncio

app = QtWidgets.QApplication(sys.argv)
p = QtWidgets.QProgressBar()
p.show()


async def work():
    for i in range(101):
        p.setValue(i)
        print(i)
        await asyncio.sleep(.05)


async def ui():
    app.exec()


async def main():
    task1 = asyncio.create_task(work())
    task2 = asyncio.create_task(ui())

    await task1
    await task2

asyncio.run(main())





