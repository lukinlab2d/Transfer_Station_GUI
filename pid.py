MIN_V = 0
MAX_V = 24 # max voltage in V

class PID:
    def __init__(self, Kc = 0.0, Ki = 0.0, Kd = 0.0):

        self._set_point = 0
        self._Kc = Kc
        self._Ki = Ki
        self._Kd = Kd
        self._curr_time = None
        self._prev_time = 0
        self._i_error = 0.0
        self._pv_error = 0.0
        self._output = 0.0
        self._later_sp = 0

    def update(self, t, process_value):
        self._curr_time = t
        self._error = self._set_point - process_value
        self._later_error = self._later_sp - process_value
        weight = 0.3 # weight for later error

        if self._prev_time == 0: # first round of PID loop, no previous time
            self._output = self._Kc * ((1-weight)*self._error + weight*self._later_error) # no integral or derivative terms
            if self._output < MIN_V or self._output > MAX_V:
                self._output = max(MIN_V, min(MAX_V, self._output))
        else:
            self._dt = self._curr_time - self._prev_time
            self._i_error = self._i_error + self._Ki * (self._pv_error + self._error) / 2 * self._dt
            self.der = (self._error - self._pv_error) / self._dt
            self._output = (1-weight) * (self._Kc * self._error + self._i_error + self._Kd * self.der) + weight * self._Kc * self._later_error
            # if output is out of range
            if self._output < MIN_V:
                self._output = MIN_V
                self._i_error = MIN_V - self._Kc * self._error - self._Kd * self.der
            elif self._output > MAX_V:
                self._output = MAX_V
                self._i_error = MAX_V - self._Kc * self._error - self._Kd * self.der

        self._pv_error = self._error
        self._prev_time = self._curr_time
        return self._output

    def set_tunning(self, kc, taui, taud):
        self._Kc = kc
        self._Ki = taui
        self._Kd = taud

    def set_p(self, p):
        self._Kc = p

    def set_setpoint(self, setpoint):
        self._set_point = setpoint

    def set_later_sp(self, sp):
        self._later_sp = sp

    def get_setpoint(self):
        return self._set_point

    @property
    def get_output(self):
        return self._output