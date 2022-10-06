from PyQt5.QtWidgets import (
    QWidget, QApplication, QProgressBar, QMainWindow,
    QHBoxLayout, QPushButton
)
from PyQt5.QtCore import (
    Qt, QTimer, QObject, pyqtSignal, pyqtSlot, QRunnable, QThreadPool
)
from PyQt5 import QtGui
import pyqtgraph as pg
import time
import subprocess
import numpy
import sys
import pid_ui
import qtmodern.styles
import qtmodern.windows
from TenmaDC import Tenma
from Thermometer import Thermometer
from pid import PID

PORT = 4 # port number for power supply
NUM_POINTS_PLOT = 2000 # number of points on the plot


class WorkerSignals(QObject):
    current_temp = pyqtSignal(float, float, float) # [time, temp, setpoint] tuple
    current_v = pyqtSignal(float, float, float, float) # [time, temp, voltage, setpoint] tuple

class JobRunner(QRunnable):
    def __init__(self, ui: pid_ui.Ui_MainWindow, thermometer: Thermometer, power_supply: Tenma, status):
        super().__init__()
        self.tenma = power_supply
        self.thermometer = thermometer
        self.ui = ui
        self.status = status
        self.t0 = None
        self.initial_sp = None
        self.current_sp = None
        self.signals = WorkerSignals()
        self.temp = None

        try:
            self.sp = float(self.ui.sp_edit.text())
            self.ramp_rate = float(self.ui.ramp_rate_edit.text())
            self.p = float(self.ui.edit_p.text())
            self.i = float(self.ui.edit_i.text())
            self.d = float(self.ui.edit_d.text())
            self.pid = PID(self.p, self.i, self.d)
            self.v = 0
            self.v_ramp_time = 0
            if self.ui.tabWidget.currentIndex() == 1:
                self.v = float(self.ui.v_edit.text())
                self.v_ramp_time = float(self.ui.ramp_time_edit.text()) * 60 # ramp time in seconds
        except ValueError:
            pass # error message will be printed in the run function

        self.ui.pauseBtn.clicked.connect(self.pause)
        self.ui.edit_p.returnPressed.connect(self.update_p)
        self.ui.edit_i.returnPressed.connect(self.update_i)
        self.ui.edit_d.returnPressed.connect(self.update_d)

    def pause(self):
        # change the colors of the buttons upon clicked
        self.ui.pauseBtn.setStyleSheet("background-color: green")
        self.ui.startBtn.setStyleSheet("")
        self.ui.stopBtn.setStyleSheet("")

        if self.status[0] == 0 and self.ui.tabWidget.currentIndex() == 0:
            self.ui.lcd2.display(str(round(self.current_sp, 2))) # update lcd display
            self.ui.lcd5.display('0')
        self.status[0] = 1

    def update_p(self):
        try:
            self.p = float(self.ui.edit_p.text())
        except ValueError:
            print('P value is empty/invalid.')
            self.stop()

    def update_i(self):
        try:
            self.i = float(self.ui.edit_i.text())
        except ValueError:
            print('I value is empty/invalid.')
            self.stop()

    def update_d(self):
        try:
            self.d = float(self.ui.edit_d.text())
        except ValueError:
            print('D value is empty/invalid.')
            self.stop()


    @pyqtSlot()
    def run(self):
        try: # if GUI exit is suddenly pressed
            prev_mode = None
            prev_status = None
            ramp_i = -1 # initial point of voltage ramp
            while self.status[0] != 2: # not at stop status
                try:
                    self.temp = self.thermometer.get_temp()
                except subprocess.CalledProcessError:
                    print("usbtenkiget error")
                    self.stop()
                    break
                t = time.time()
                current_mode = self.ui.tabWidget.currentIndex()
                if current_mode == 1: # voltage mode
                    if self.status[0] == 0:
                        if prev_mode == 0:
                            self.ui.modeComboBox.setCurrentText('Fixed voltage')
                            self.v = self.tenma.runningVoltage()  # if changing from pid mode, keep the same voltage
                            self.ui.v_edit.setText(str(self.v))
                            self.ui.lcd3.display(str(self.v))
                        if self.ui.modeComboBox.currentText() == 'Ramp voltage' and self.v_ramp_time != None and self.v_ramp_time != 0:
                            if ramp_i == -1: # ramp just starts, the initial V point is the current voltage
                                ramp_i = self.tenma.runningVoltage()
                                self.t0 = time.time()
                            if time.time() - self.t0 <= self.v_ramp_time:
                                V = ramp_i + (self.v - ramp_i) / self.v_ramp_time * (time.time() - self.t0) # V is the currently set voltage
                            else: # exceed the theoretical ramp time
                                V = self.v
                                self.v_ramp_time = 0
                                self.ui.modeComboBox.setCurrentText('Fixed voltage')
                                self.ui.ramp_time_edit.setText('')
                                self.t0 = None
                                ramp_i = -1
                        else: # fixed voltage mode
                            V = self.v
                    else: # status = pause
                        V = self.tenma.runningVoltage()
                        ramp_i = -1
                    self.tenma.setVoltage(V)
                    self.signals.current_v.emit(t, self.temp, V, self.pid.get_setpoint())  # update voltage display
                    prev_mode = 1

                else: # PID mode
                    if prev_mode == None: # just start
                        self.t0 = time.time()
                        self.initial_sp = self.thermometer.get_temp()
                    elif prev_mode == 1:
                        self.status[0] = 2
                        self.ui.stopBtn.setStyleSheet("background-color: green")
                        self.ui.startBtn.setStyleSheet("")
                        self.ui.pauseBtn.setStyleSheet("")
                        self.tenma.setVoltage(0)  # zero the output voltage
                        break
                    try:
                        if self.status[0] == 0:
                            if prev_status == 1:
                                self.t0 = time.time()
                                self.initial_sp = self.thermometer.get_temp()
                            if self.sp > self.initial_sp:
                                self.current_sp = min(self.initial_sp + self.ramp_rate / 60 * (time.time() - self.t0), self.sp)
                                self.pid.set_setpoint(self.current_sp)
                                self.pid.set_later_sp(min(self.initial_sp + self.ramp_rate / 60 * (time.time() + 20 - self.t0), self.sp))
                            else:
                                self.current_sp = max(self.initial_sp - self.ramp_rate / 60 * (time.time() - self.t0), self.sp)
                                self.pid.set_setpoint(self.current_sp)
                                self.pid.set_later_sp(max(self.initial_sp - self.ramp_rate / 60 * (time.time() + 20 - self.t0), self.sp))
                            prev_status = 0
                        elif self.status[0] == 1:
                            self.pid.set_setpoint(self.current_sp)
                            self.pid.set_later_sp(self.current_sp)
                            prev_status = 1
                    except AttributeError:
                        print('PID values are empty/invalid.')  # PID initializations failed
                        self.stop()
                        break

                    self.pid.set_tunning(self.p, self.i, self.d)
                    V = self.pid.update(t, self.temp)
                    self.tenma.setVoltage(V)
                    self.signals.current_temp.emit(t, self.temp, self.pid.get_setpoint())  # plot
                    prev_mode = 0
        except RuntimeError:
            pass

    def stop(self):
        # change the colors of the buttons upon clicked
        self.ui.stopBtn.setStyleSheet("background-color: green")
        self.ui.startBtn.setStyleSheet("")
        self.ui.pauseBtn.setStyleSheet("")

        self.status[0] = 2
        self.ui.lcd2.display('0')  # update lcd display
        self.ui.lcd3.display('0')
        self.ui.lcd5.display('0')
        time.sleep(0.2)
        self.tenma.setVoltage(0) # zero the output voltage

    def start(self):
        self.status[0] = 0


class MainWindow(QMainWindow):

    def __init__(self):
        super(MainWindow, self).__init__()
        self.ui = pid_ui.Ui_MainWindow()
        self.ui.setupUi(self)
        self.thermometer = Thermometer()
        self.tenma = Tenma(PORT)
        self.status = [2] # [0 1 2] = [start pause stop], defined as a list to pass to functions as reference

        self.ui.tempPlot.setBackground((25,25,25))
        self.ui.tempPlot.setLabel("bottom", "Time", "s")
        self.ui.tempPlot.setLabel("left", "Temperature", "C")
        self.ui.tempPlot.showGrid(True, True, 0.8)
        self.ui.tempPlot.addLegend()
        pen = pg.mkPen(color='w', width=2.0)
        pen2 = pg.mkPen(color='r', width=2.0)

        self.x = [0] * NUM_POINTS_PLOT # time
        self.y = [0] * NUM_POINTS_PLOT # temperature
        self.z = [0] * NUM_POINTS_PLOT # setpoint
        self.data_line = self.ui.tempPlot.plot(self.x, self.y, pen=pen, name='temperature')
        self.sp_line = self.ui.tempPlot.plot(self.x, self.z, connect="finite", pen=pen2, name='setpoint')
        self.t0 = time.time() # start time

        # Thread runner
        self.threadpool = QThreadPool()

        self.ui.startBtn.clicked.connect(self.start)
        self.ui.stopBtn.clicked.connect(self.stop)
        self.ui.saveBtn.clicked.connect(self.savePID)
        self.ui.plusBtn.clicked.connect(self.plus_sp)
        self.ui.minusBtn.clicked.connect(self.minus_sp)
        self.ui.setBtn.clicked.connect(self.update)
        self.ui.setvBtn.clicked.connect(self.update_v)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_without_PID)
        self.timer.start(200) # interval 0.2s

    def update(self):
        try:
            if self.status[0] == 2: # at stop status
                self.ui.lcd2.display(self.ui.sp_edit.text())
                self.ui.lcd5.display(self.ui.ramp_rate_edit.text())
            else:
                self.runner.sp = float(self.ui.sp_edit.text())
                self.runner.ramp_rate = float(self.ui.ramp_rate_edit.text())
                self.ui.lcd2.display(str(round(self.runner.sp, 2)))
                self.ui.lcd5.display(str(self.runner.ramp_rate))
                self.runner.initial_sp = self.runner.temp # if setpoint or ramp rate is re-defined, need to update
                self.runner.t0 = time.time()
        except ValueError:
            print('Setpoint or ramp rate is empty/invalid.')
            self.stop()

    def update_v(self):
        try:
            if self.status[0] != 2:
                self.runner.v = float(self.ui.v_edit.text())
                self.runner.v_ramp_time = float(self.ui.ramp_time_edit.text()) * 60
        except ValueError:
            pass

    def start(self):
        self.ui.startBtn.setStyleSheet("background-color: green")
        self.ui.pauseBtn.setStyleSheet("")
        self.ui.stopBtn.setStyleSheet("")

        if self.status[0] == 2: # currently in stop mode
            self.runner = JobRunner(self.ui, self.thermometer, self.tenma, self.status)
            self.runner.signals.current_temp.connect(self.update_with_PID)
            self.runner.signals.current_v.connect(self.update_with_voltage)
            self.runner.start()
            time.sleep(0.2) # wait for current round of self.update_without_PID to finish
            self.threadpool.start(self.runner)
        self.status[0] = 0


    def stop(self):
        if self.status[0] == 0 or self.status[0] == 1:
            self.runner.stop()

    def savePID(self):
        saveFile = open("pid_ui.py", "a")
        saveFile.write('\n# ' + self.ui.edit_p.text() + ' ' + self.ui.edit_i.text() + ' ' + self.ui.edit_d.text())
        saveFile.close()

    def plus_sp(self):
        try:
            self.ui.sp_edit.setText(str(float(self.ui.sp_edit.text()) + 1))
            if self.status[0] != 2:
                self.runner.initial_sp = self.runner.temp  # if setpoint or ramp rate is re-defined, need to update
                self.runner.t0 = time.time()
                self.runner.sp = float(self.ui.sp_edit.text())
        except ValueError:
            print('setpoint value is empty/invalid.')

    def minus_sp(self):
        try:
            self.ui.sp_edit.setText(str(float(self.ui.sp_edit.text()) - 1))
            if self.status[0] != 2:
                self.runner.initial_sp = self.runner.temp  # if setpoint or ramp rate is re-defined, need to update
                self.runner.t0 = time.time()
                self.runner.sp = float(self.ui.sp_edit.text())
        except ValueError:
            print('setpoint value is empty/invalid.')

    def update_without_PID(self):
        if self.status[0] == 2:
            try:
                temp = self.thermometer.get_temp()
            except: # just finish run, used get_temp() in the runner
                time.sleep(0.5)
                temp = self.thermometer.get_temp()
            self.x = self.x[1:]  # Remove the first
            self.x.append(time.time() - self.t0)
            self.y = self.y[1:]
            self.y.append(temp)
            self.z = self.z[1:]
            self.z.append(numpy.nan)  # append null point for setpoint array
            self.data_line.setData(self.x, self.y)  # Update the plot
            self.sp_line.setData(self.x, self.z)
            self.ui.lcd.display(str(temp)) # update the temp display
            self.ui.lcd4.display(str(temp))  # update the temp display

    def update_with_voltage(self, t, temp, V, setpoint):
        self.x = self.x[1:]  # Remove the first
        self.x.append(t - self.t0)
        self.y = self.y[1:]
        self.y.append(temp)
        self.z = self.z[1:]
        if setpoint == 0:
            self.z.append(numpy.nan)  # append null point for setpoint array
        else:
            self.z.append(setpoint)
        self.data_line.setData(self.x, self.y)  # Update the plot
        self.sp_line.setData(self.x, self.z)
        self.ui.lcd4.display(str(temp)) # update the temp display
        if self.status[0] != 2:
            self.ui.lcd3.display(str(round(V, 2)))  # display voltage


    def update_with_PID(self, t, temp, setpoint):
        self.x = self.x[1:] # Remove the first
        self.x.append(t - self.t0)
        self.y = self.y[1:]
        self.y.append(temp)
        self.z = self.z[1:]
        self.z.append(setpoint)
        self.data_line.setData(self.x, self.y) # Update the plot
        self.sp_line.setData(self.x, self.z)
        self.ui.lcd.display(str(temp)) # update the temp display
        if self.status[0] == 0:
            self.ui.lcd2.display(str(round(setpoint, 2)))  # update the setpoint display



def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    mainW = MainWindow()
    qtmodern.styles.dark(app)
    mw = qtmodern.windows.ModernWindow(mainW)
    try:
        mw.show()
        sys.exit(app.exec_())
    finally: # in case the GUI exits without pressing stop, need to zero the voltage
        try:
            mainW.tenma.setVoltage(0)
            mainW.tenma.close()
        except:
            pass



if __name__ == '__main__':         
    main()