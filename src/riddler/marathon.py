
from dataclasses import dataclass
from datetime import datetime, timedelta
from discord import Member, Role, app_commands as apc, Interaction, Attachment
from discord.ext import commands
from itertools import product as list_product
from os import makedirs
from riddler import embeds
from riddler.jsonable import DotDict, JSONable
from typing import TYPE_CHECKING, List, Literal, Optional, Tuple, Dict
from yaml import load as yaml_load, dump as yaml_dump, Loader, Dumper, SafeDumper

if TYPE_CHECKING:
    from riddler import Riddler

async def setup(bot: 'Riddler'):
    await bot.add_cog(Marathon(bot))



@dataclass
class Team(DotDict, JSONable):
    """
    Maps a team to their members.
    """
    name: str
    members: List[int]
    channels: List[int]
    role: Dict[int, int]

    def __init__(self, *, name: str, members: List[int], channels: List[int], role = None) -> None:
        self.name = name 
        self.members = members
        self.channels = channels
        self.role = role or {}

    def includes(self, snowflake: int) -> bool:
        return snowflake in self.members    

    def repr(self, interaction: Interaction) -> str:
        if interaction.guild_id in self.role: return f'<@&{self.role[interaction.guild_id]}>'
        return self.name

@dataclass
class Puzzle(DotDict, JSONable):
    """
    The public definition of a puzzle.
    """
    id: str
    name: str
    category: str
    points: int
    url: str

    def __init__(self, *, id: str, name: str, category: str, points: int, url: str) -> None:
        self.id = id
        self.name = name 
        self.category = category
        self.points = points
        self.url = url

    def __repr__(self) -> str:
        return f'{self.id}: {self.name}'

AttemptState = Literal['not started', 'in progress', 'submitted']
"""
The states a puzzle can be in.
    - not-started is a puzzle that has not been `/unlock`ed by a team yet.
    - in-progress is a puzzle that has been selected with `/unlock`.
    - submitted is a puzzle that has been submitted with `/submit`.
"""

@dataclass
class AttemptTimer(DotDict, JSONable):
    """
    Stores and computes timer information.
    """
    start: Optional[datetime]
    end: Optional[datetime]
    duration: Optional[str]

    def __init__(self, *, start: Optional[int] = None, end: Optional[int] = None, duration: Optional[str] = None) -> None:
        self.start = start
        self.end = end
        self.duration = duration

    def unlock(self) -> None:
        self.start = datetime.now()
    
    def submit(self) -> None:
        self.end = datetime.now()
        self.duration = str(self.end - self.start)

    # Dealing with datetimes

    def dump(self):
        data: AttemptTimer = super().dump()
        if data.start: data.start = str(data.start)
        if data.end: data.end = str(data.end)
        return data

    @classmethod
    def load(cls, json_value):
        inst = cls(**json_value)
        if inst.start: inst.start = datetime.fromisoformat(inst.start)
        if inst.end: inst.end = datetime.fromisoformat(inst.end)
        return inst

@dataclass
class Attempt(DotDict, JSONable):
    """
    The relation describing a team's attempt at solving a particular puzzle.
    """
    puzzle: str
    team: str
    state: AttemptState
    timer: AttemptTimer
    link: Optional[str]

    def __init__(self, *, puzzle: str, team: str, state: AttemptState, timer: dict = {}, link: Optional[str] = None) -> None:
        self.puzzle = puzzle
        self.team = team
        self.state = state
        self.timer = AttemptTimer(**timer)
        self.link = link

    def unlock(self) -> None:
        self.state = 'in progress'
        self.timer.unlock()
    
    def submit(self, link: str) -> None:
        self.state = 'submitted'
        self.timer.submit()
        self.link = link

AttemptDict = Dict[str, Dict[str, Attempt]]
"""
A mapping of (puzzle.id, team.name) to the corresponding attempt.
"""

class Marathon(commands.GroupCog, group_name='marathon'):
    """
    A cog that handles authenticated puzzle-fetching for the marathon.
    """    
    
    def __init__(self, bot: 'Riddler') -> None:
        self.bot = bot

    # AUTOCOMPLETION
    
    async def autocomplete_teams(self, interaction: Interaction, partial: str):
        """
        Returns a list of teams.
        """
        _, _, teams = self.load()
        return [apc.Choice(name=team.name, value=team.name) for team in teams.values() if partial in team.name]

    def repr_puzzle(self, puzzle: Puzzle) -> str:
        return f'#{puzzle.id}: "{puzzle.name}"'

    async def autocomplete_unlockable(self, interaction: Interaction, partial: str):
        """
        Returns a list of puzzles not yet started by the given team.
        """
        attempts, puzzles, teams = self.load()
        team = self.find_team(interaction.user, teams)
        if not team:
            return []

        unlockables = [puzzle for puzzle in puzzles.values() if attempts[puzzle.id][team.name].state == 'not started']
        filtered = [puzzle for puzzle in unlockables if partial in self.repr_puzzle(puzzle)]
        return [apc.Choice(name=self.repr_puzzle(puzzle), value=puzzle.id) for puzzle in filtered]

    async def autocomplete_submittable(self, interaction: Interaction, partial: str):
        """
        Returns a list of in-progress puzzles that are yet to be submitted.
        """
        attempts, puzzles, teams = self.load()
        team = self.find_team(interaction.user, teams)
        if not team:
            return []
        
        submittables = [puzzle for puzzle in puzzles.values() if attempts[puzzle.id][team.name].state == 'in progress']
        filtered = [puzzle for puzzle in submittables if partial in self.repr_puzzle(puzzle)]
        return [apc.Choice(name=self.repr_puzzle(puzzle), value=puzzle.id) for puzzle in filtered]

    # COMMANDS

    @apc.command()
    @apc.autocomplete(team=autocomplete_teams)
    @apc.describe(team='the team to configure')
    async def add_channel(self, interaction: Interaction, team: str):
        """
        Add a channel to a team
        """
        if not await self.ensure_owner(interaction):
            return
        
        attempts, _, teams = self.load()
        if interaction.channel_id not in teams[team].channels:
            teams[team].channels.append(interaction.channel_id)
        self.store(attempts=attempts, teams=teams)

        await self.send_ethereal(interaction, description=f'Added this channel to {teams[team].repr(interaction)}.')

    @apc.command()
    @apc.autocomplete(team=autocomplete_teams)
    @apc.describe(team='the team to configure')
    async def remove_channel(self, interaction: Interaction, team: str):
        """
        Remove a channel from a team
        """
        if not await self.ensure_owner(interaction):
            return
        
        attempts, _, teams = self.load()
        if interaction.channel_id in teams[team].channels:
            teams[team].channels.remove(interaction.channel_id)
        self.store(attempts=attempts, teams=teams)

        await self.send_ethereal(interaction, description=f'Removed this channel from {teams[team].repr(interaction)}.')

    @apc.command()
    @apc.autocomplete(team=autocomplete_teams)
    @apc.describe(team='the team to inspect')
    async def list_players(self, interaction: Interaction, team: str):
        """
        List all players on a team
        """
        _, _, teams = self.load()
        members = '\n'.join(list(map(lambda m: f'- <@{m}>', teams[team].members)))
        description = f'__{teams[team].repr(interaction)} members__\n{members}' if members != '' else f'There are no players on {teams[team].repr(interaction)}.'
        await self.send_ethereal(interaction, ethereal=False, description=description)

    @apc.command()
    @apc.autocomplete(team=autocomplete_teams)
    @apc.describe(player='the player to add')
    @apc.describe(team='the team to configure')
    async def add_player(self, interaction: Interaction, player: Member, team: str):
        """
        Add a player to a team
        """
        if not await self.ensure_owner(interaction):
            return
        
        attempts, _, teams = self.load()
        curr = self.find_team(player, teams)
        if curr is not None:
            return await self.send_ethereal(interaction, description=f'{player.mention} is already on {curr.repr(interaction)}.')
        
        teams[team].members.append(player.id)
        self.store(attempts=attempts, teams=teams)

        await self.send_ethereal(interaction, description=f'Added {player.mention} to {teams[team].repr(interaction)}.')

    @apc.command()
    @apc.autocomplete(team=autocomplete_teams)
    @apc.describe(player='the player to remove')
    @apc.describe(team='the team to configure')
    async def remove_player(self, interaction: Interaction, player: Member, team: str):
        """
        Remove a player from a team
        """
        if not await self.ensure_owner(interaction):
            return
        
        attempts, _, teams = self.load()
        curr = self.find_team(player, teams)
        if curr is None:
            return await self.send_ethereal(interaction, description=f'{player.mention} is not on a team.')
        
        if teams[team].includes(player.id):
            teams[team].members.remove(player.id)
        self.store(attempts=attempts, teams=teams)

        await self.send_ethereal(interaction, description=f'Removed {player.mention} from {curr.repr(interaction)}.')

    @apc.command()
    @apc.autocomplete(team=autocomplete_teams)
    @apc.describe(team='the team to configure')
    @apc.describe(role='the team role')
    async def set_role(self, interaction: Interaction, team: str, role: Role):
        """
        Set a team role.
        """
        if not await self.ensure_owner(interaction):
            return
        
        attempts, _, teams = self.load()
        teams[team].role[interaction.guild_id] = role.id
        self.store(attempts=attempts, teams=teams)

        await self.send_ethereal(interaction, description=f'Team "{team}" set to {teams[team].repr(interaction)} in this server.')

    @apc.command()
    @apc.describe(puzzles='a puzzles.yaml file')
    @apc.describe(teams='a teams.yaml file')
    async def initialize(self, interaction: Interaction, puzzles: Attachment, teams: Attachment):
        """
        Initialize a set of puzzles and teams
        """
        if not await self.ensure_owner(interaction):
            return
    
        try:
            puzzle_data, team_data = yaml_load(await puzzles.read(), Loader=Loader), yaml_load(await teams.read(), Loader=Loader)
        except Exception as e:
            return await interaction.response.send_message(embed=embeds.make_error(self.bot, message='Failed to load yaml file', error=e), ephemeral=True, delete_after=5)

        puzzle_dict, team_dict = { k: Puzzle(**{**v, 'id': k}) for k, v in puzzle_data.items() }, { k: Team(**{**v, 'name': k}) for k, v in team_data.items() }
        attempts = { pk: { tk: Attempt(puzzle=pk, team=tk, state='not started') for tk, team in team_dict.items() } for pk, puzzle in puzzle_dict.items() }

        await self.send_ethereal(interaction, ethereal=False, description=f'Initialized {len(puzzle_dict)} puzzles for {len(team_dict)} teams.')

        self.store(attempts=attempts, puzzles=puzzle_dict, teams=team_dict)

    @apc.command()
    @apc.autocomplete(puzzle=autocomplete_unlockable)
    @apc.describe(puzzle="the puzzle")
    async def unlock(self, interaction: Interaction, puzzle: str):
        """
        Unlock a puzzle and start solving
        """
        attempts, puzzles, teams = self.load()

        team = await self.ensure_team(interaction, teams)
        if not team: 
            return

        if not await self.ensure_channel(interaction, team):
            return

        relevant_attempt = attempts[puzzle][team.name]

        if not await self.ensure_state(interaction, relevant_attempt.state, 'not started'):
            return

        relevant_attempt.unlock()
        url = puzzles[relevant_attempt.puzzle].url
        name = puzzles[relevant_attempt.puzzle].name

        await self.send_ethereal(interaction, ethereal=False, ephemeral=False, title=f'#{puzzle}: {name}', description=f"Here's a [link to the puzzle]({url}).")

        attempts[puzzle][team.name] = relevant_attempt

        self.store(attempts=attempts)

    @apc.command()
    @apc.autocomplete(puzzle=autocomplete_submittable)
    @apc.describe(puzzle='the puzzle')
    @apc.describe(link='a message link for your solution')
    async def submit(self, interaction: Interaction, puzzle: str, link: str):
        """
        Submit a solution to an unlocked puzzle
        """
        attempts, puzzles, teams = self.load()

        team = await self.ensure_team(interaction, teams)
        if not team:
            return
        
        if not await self.ensure_channel(interaction, team):
            return
        
        relevant_attempt = attempts[puzzle][team.name]

        if not await self.ensure_state(interaction, relevant_attempt.state, 'in progress'):
            return
        
        relevant_attempt.submit(link)
        duration = relevant_attempt.timer.duration
        name = puzzles[relevant_attempt.puzzle].name

        await self.send_ethereal(interaction, ethereal=False, ephemeral=False, title=f'#{puzzle}: {name}', description=f'```elapsed: {duration}```')

        attempts[puzzle][team.name] = relevant_attempt

        self.store(attempts=attempts)

    # HELPERS

    async def ensure_channel(self, interaction: Interaction, team: Team) -> bool:
        """
        Ensures the team is using commands in a channel registered to them.
        """
        id = interaction.channel_id
        if id not in team.channels:
            allowed_channels = '\n'.join(f'- <#{ch}>' for ch in team.channels)
            await interaction.response.send_message(embed=embeds.make_error(self.bot, message=f'You are not allowed to do that in this channel. Try one of these:\n{allowed_channels}'))
            return False
        return True

    async def ensure_owner(self, interaction: Interaction) -> bool:
        """
        Checks that the user is a bot owner.
        """
        if interaction.user.id not in self.bot.owner_ids: 
            await interaction.response.send_message(embed=embeds.unauthorized(self.bot, message='You need to be an Organizer to do that.'), ephemeral=True, delete_after=5)
            return False
        return True

    async def ensure_state(self, interaction: Interaction, state: AttemptState, expected: AttemptState) -> bool:
        """
        Checks that a team's attempt on a puzzle is in a given state.
        """
        if state != expected:
            await interaction.response.send_message(embed=embeds.make_error(self.bot, message=f'This puzzle is {state}; expected it to be {expected}!'), ephemeral=True, delete_after=5)
            return False
        return True

    async def ensure_team(self, interaction: Interaction, teams: Dict[str, Team]) -> Optional[Team]:
        """
        Checks that the user is a member of an active team, and responds if not.
        """
        team = self.find_team(interaction.user, teams)
        if not team:
            await interaction.response.send_message(embed=embeds.unauthorized(self.bot, message='You need to be on a team to do that.'), ephemeral=True, delete_after=5)
        return team

    def find_team(self, member: Member, teams: Dict[str, Team]) -> Optional[Team]:
        """
        Determines if the user is on an active team or not.
        """
        for team in teams.values():
            # By common role
            role_ids = [r for r in team.role.values()]
            if any(r.id in role_ids for r in member.roles): 
                return team
            # By user
            if team.includes(member.id):
                return team
        return None

    async def send_ethereal(self, interaction: Interaction, *, followup = False, ethereal = True, ephemeral = True, **kwargs):
        """
        Sends an autodeleting, ephemeral message.
        """
        if 'title' in kwargs:
            await self.bot.send_ethereal(interaction, followup=followup, ethereal=ethereal, ephemeral=ephemeral, **kwargs)
        else:
            await self.bot.send_ethereal(interaction, followup=followup, ethereal=ethereal, ephemeral=ephemeral, title='Puzzle Marathon', **kwargs)

    # IO

    def load(self) -> Tuple[AttemptDict, Dict[str, Puzzle], Dict[str, Team]]:
        def _load(path: str):
            with open('data/marathon/' + path, 'r') as src:
                return yaml_load(src, Loader=Loader)
        
        attempts = _load('attempts.yaml')
        puzzles = _load('puzzles.yaml')
        teams = _load('teams.yaml')
        return attempts, puzzles, teams

    def store(self, *, attempts, puzzles = None, teams = None):
        class NoAliasDumper(SafeDumper):
            def ignore_aliases(self, data):
                return True

        def _store(obj: dict, path: str):
            with open('data/marathon/' + path, 'w') as dest:
                yaml_dump(obj, dest, Dumper=NoAliasDumper)
        
        makedirs('data/marathon', exist_ok=True)
        _store(attempts, 'attempts.yaml')
        if puzzles: _store(puzzles, 'puzzles.yaml')
        if teams: _store(teams, 'teams.yaml')
