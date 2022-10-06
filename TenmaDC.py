import pyvisa as visa
import pyvisa.errors
import time


class Tenma(object):
    def __init__(self, port):
        rm = visa.ResourceManager()
        try:
            self.power_supply = rm.open_resource('ASRL' + str(port) + '::INSTR')
        except:
            print('cannot open the port')
            pass
        self.power_supply.baud_rate = 9600

    def setVoltage(self, V):
        self.power_supply.write('VSET1:' + str(V))
        time.sleep(0.1)

    def runningCurrent(self): # return the actual output current and voltage
        return float(self.power_supply.query('IOUT1?'))

    def runningVoltage(self):
        return float(self.power_supply.query('VOUT1?'))

    def close(self):
        self.power_supply.close()
        self.power_supply = None
