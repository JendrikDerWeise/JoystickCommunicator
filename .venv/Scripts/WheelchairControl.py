import random

class WheelchairControl:
    wheelchair_speed = 0
    actual_gear = 1
    count_float: float = 0.00
    up_down = 1
    epsilon = 0.001
    light_on = False
    warn_on = False
    horn_on = False
    kantelung_on = False

    def __init__(self):
        self.wheelchair_speed = 0

    def on_kantelung(self, on):
        self.kantelung_on = on
        print("kantelung " + str(self.kantelung_on))

    def get_kantelung(self):
        return self.kantelung_on

    def on_horn(self, on):
        self.horn_on = on
        print("HUP! " + str(on))

    def set_warn(self):
        self.warn_on = not self.warn_on

    def get_warn(self):
        return self.warn_on

    def set_lights(self):
        self.light_on = not self.light_on

    def get_lights(self):
        return self.light_on

    def get_wheelchair_speed(self) -> float:
        if self.up_down == 1:
            self.count_float += 0.01
        if self.up_down == 0:
            self.count_float -= 0.01
        if self.count_float >= 6.00:
            self.up_down = 0
        if self.count_float <= 0.00:
            self.up_down = 1
        #return self.wheelchair_speed
        return self.count_float

    def random_float(self):
        rand = round(random.uniform(0, 6), 2)
        rand = min(rand, 6.00)
        return rand

    def set_direction(self, direction):
        i = 0
        #print("Joystick pos: " + str(direction))

    def set_gear(self, gearUp):
        if gearUp:
            if self.actual_gear < 5:
                self.actual_gear += 1
        else:
            if self.actual_gear > 1:
                self.actual_gear -= 1

        return self.actual_gear