import json
import time

from .game_map import GameMap
from .user import User
from .position import Position
from .building import get_building_class

from .constants import ROUND_TIME, GAME_WIDTH, GAME_HEIGHT, GAME_MAX_TURN
from .constants import CMD_ATTACK, CMD_BUILD

class Colorfight:
    def __init__(self):
        self.turn = 0
        self.max_turn = GAME_MAX_TURN
        self.width = GAME_WIDTH
        self.height = GAME_HEIGHT
        self.round_time = ROUND_TIME
        self.last_update = time.time()
        self.users = {}
        self.errors = {}
        self.game_map = GameMap(self.width, self.height)
        self.valid_actions = {
            "register": [("username", "password"), ("uid",)],
            "command": [("cmd_list",), ()]
        }
    
    def get(self):
        return self.counter

    def restart(self):
        self.turn = 0
        self.users = {}
        self.errors = {}
        self.game_map = GameMap(self.height, self.width) 

    def update(self, force = False):
        if force or \
                (time.time() - self.last_update > self.round_time and self.turn < self.max_turn):
            self.last_update = time.time()
            self.turn += 1
            self.errors = self.do_all_commands()
            # 1. Update all the cells based on attackers
            #    This will also update the cell dict in users
            #    and the energy/gold income for a user
            self.update_cells()
            # 2. Update all the users for gold and energy
            self.update_users()

    def update_cells(self):
        self.game_map.update_cells(self.users)

    def update_users(self):
        for user in self.users.values():
            user.update()

    '''
    This is the game command part.
    We currently have:
        ATTACK
        BUILD
    '''
    def do_all_commands(self):
        errors = {}
        for user in self.users.values():
            errors[user.uid] = []
            for cmd in user.cmd_list:
                result = self.do_command(user.uid, cmd)
                if result != None:
                    errors[user.uid].append(result)
        return errors
                    
    def do_command(self, uid, cmd):
        err_msg = ""

        try: 
            arg_list = cmd.split() 
        except:
            return "{} is not a command".format(cmd)

        if len(arg_list) == 0:
            return "{} is not a command".format(cmd)

        try:
            cmd_type = arg_list[0]
            if cmd_type == CMD_ATTACK:
                x = int(arg_list[1])
                y = int(arg_list[2])
                energy = int(arg_list[3])
                result, err_msg = self.cmd_attack(uid, x, y, energy)
            elif cmd_type == CMD_BUILD:
                x = int(arg_list[1])
                y = int(arg_list[2])
                building = arg_list[3]
                result, err_msg = self.cmd_build(uid, x, y, building)
            else:
                return "{} is a wrong command, cmd type {} is invalid".format(cmd, cmd_type)
        except Exception as e:
            return "{} is a wrong command, {}".format(cmd, e)

        if not result:
            return "{} failed, {}.".format(cmd, err_msg)
        return None

    def cmd_attack(self, uid, x, y, energy):
        atk_pos = Position(x, y)

        if atk_pos not in self.game_map:
            return False, "Attack position is not in the map"

        if energy < self.game_map[atk_pos].attack_cost:
            return False, "The energy spent is less than attack cost"

        if energy > self.users[uid].energy:
            return False, "Do not have enough energy to attack"

        for pos in atk_pos.valid_surrounding_cardinals():
            if self.game_map[pos].owner == uid:
                self.users[uid].energy -= energy 
                self.game_map[(x, y)].attack(uid, energy)
                return True, ""
        return False, "No valid surrounding cell to attack"

    def cmd_build(self, uid, x, y, building):
        build_pos = Position(x, y)

        if build_pos not in self.game_map:
            return False, "Build position is not in the map"

        if self.game_map[build_pos].owner != uid:
            return False, "You need to build on your own cell"

        if not self.game_map[build_pos].building.is_empty():
            return False, "There is a building on this cell already"

        BldClass = get_building_class(building)
        if BldClass is None:
            return False, "Not a correct building"

        if self.users[uid].gold < BldClass.cost:
            return False, "Not enough gold"

        self.game_map[build_pos].building = BldClass()
        self.users[uid].gold -= BldClass.cost

        return True, ""

    '''
    Possible user actions, after parse_action()
        register
        command
    '''
    def register(self, uid, username, password):
        # Check whether user exists first
        for user in self.users.values():
            if user.username == username and user.password == password:
                return True, (user.uid,)
        for uid in range(1, len(self.users) + 2):
            if uid not in self.users:
                user = User(uid, username, password)
                if self.game_map.born(user):
                    self.users[uid] = user
                    return True, (uid,)
                else:
                    return False, "Map is full"
        raise Exception("Should never be here")

    def command(self, uid, cmd_list):
        if type(cmd_list) != list:
            return False, "Wrong type"
        if uid not in self.users:
            return False, "Wrong uid"
        self.users[uid].cmd_list = cmd_list

        return True, ()

    '''
    All the action from users
    '''
    def parse_action(self, uid, msg):
        '''
        uid is the unique id that the web server checks
        msg should be a string representing a json 
        msg is not checked for sanity at all, we need to check it
        
        return a json object
        
        '''
        try:
            data = json.loads(msg)
        except:
            return {"success": False, "err_msg":"This is not a valid json"}

        if 'action' not in data:
            return {"success": False, "err_msg":"You have to specify an action"}
        
        action = data['action']

        if action not in self.valid_actions:
            return {"success": False, "err_msg":"Not a valid action"}

        if action != 'register' and uid == None:
            return {"success": False, "err_msg":"You need to join the game first"}

        required_args = self.valid_actions[action][0]
        expected_results = self.valid_actions[action][1]
        arg_list = []
        for arg in required_args:
            if arg not in data:
                return {"success": False, "err_msg": "{} is missing".format(arg)}
            arg_list.append(data[arg])
        
        # should be a tuple 
        success, result = getattr(self, action)(uid, *arg_list)
        if not success:
            return {"success": False, "err_msg": result}
        if len(result) != len(expected_results):
            return {"success": False, "err_msg": "Server fails on {}".format(action)}
        ret = {"success": True}
        for i in range(len(result)):
            ret[expected_results[i]] = result[i]

        return ret

    '''
    Read API
    '''
    def info(self):
        return {"max_turn": GAME_MAX_TURN, \
                "width": GAME_WIDTH, \
                "height": GAME_HEIGHT}
    def get_game_info(self):
        return {\
                "turn": self.turn, \
                "info": self.info(), \
                "error": self.errors, \
                "game_map":self.game_map.info(), \
                "users": {user.uid: user.info() for user in self.users.values()} \
        }

