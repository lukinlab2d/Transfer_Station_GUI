import subprocess


class Thermometer(object):
    def get_temp(self):
        temp = subprocess.check_output(["usbtenkiget", "-i", "0"])  # read temperature using QTenki
        return float(temp[:-2])
