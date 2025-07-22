class GameState:
    def __init__(self, room_id: int, max_players: int, number_of_actions: int):
        self.room_id = room_id
        self.max_players = max_players
        self.number_of_actions = number_of_actions
        self.players = {}
        self.current_round_actions = {}
        self.eliminated_players = set()
        self.round_number = 1
        self.game_started = False
        self.game_over = False
        self.winner = None

    def add_player(self, username: str):
        if username not in self.eliminated_players:
            self.players[username] = True

    def remove_player(self, username: str):
        self.players.pop(username, None)
        self.current_round_actions.pop(username, None)

    def submit_action(self, username: str, action: int):
        if username in self.players and username not in self.eliminated_players:
            self.current_round_actions[username] = action

    def all_players_ready(self):
        active_players = [p for p in self.players if p not in self.eliminated_players]
        return (
            len(self.current_round_actions) == len(active_players)
            and len(active_players) >= 2
        )

    def get_active_players(self):
        return [p for p in self.players if p not in self.eliminated_players]

    def reset_round(self):
        self.current_round_actions = {}
        self.round_number += 1

    def reset(self):
        self.current_round_actions = {}
        self.eliminated_players = set()
        self.round_number = 1
        self.game_started = False
        self.game_over = False
        self.winner = None


game_states = {}