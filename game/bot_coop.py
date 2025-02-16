import threading
import disnake
import asyncio
import random
import json
import datetime
import os

intents = disnake.Intents.default()
intents.message_content = True

wordfiles = [f'words/{i}' for i in os.listdir("words")]
valid_words_set = set(i.split('/')[-1].split('.')[0] for i in wordfiles)
valid_words_list = list(valid_words_set)

allowed_words_set = {i.strip().lower() for i in open('words_alpha.txt', 'r').readlines()}
common_words_set = {i.strip().lower() for i in open('common_words.txt', 'r').readlines()}

BOT_TOKEN = 'MTMzOTA4NDQxMjUyODIzNDUxOQ.Gw85FW.27FKCJJVA111kzBg2qJWAmPti4JRjj5DOCbPN0'
#'OTkzNzcyMTg4OTI4ODM1Njk0.GvZKj8.GioTTeyP5suLnUyx9_zk88Pe3TjfIS5McsJVco'

async def delay_wrapper(delay, coro):
    await asyncio.sleep(delay)
    return await coro

class WordScore:
    def __init__(self, idx, score, word):
        self.word = word
        self.score = score
        self.idx = idx

    def format(self):
        return f'`{self.word}` (#{self.idx+2}, {self.score:.1f})'

    def format_find(self):
        return f'`{self.word}` found! #{self.idx+2} ({self.score:.1f})'


class Game:
    def __init__(self):
        self.secret = None
        self.guesses = set()
        self.all_guesses = set()
        self.top5000 = dict()
        self.start_time = None
        self.end_time = None

    def to_dict(self):
        return {
            "secret": self.secret,
            "guesses": list(self.guesses),
            "all_guesses": list(self.all_guesses),
            "start_time": int(self.start_time.timestamp())
        }

    @classmethod
    def from_dict(cls, dt):
        game = cls()
        game.secret = dt.get("secret")
        game.guesses = set(dt.get("guesses"))
        all_guesses = dt.get("all_guesses")
        if all_guesses is not None:
            game.all_guesses = set(all_guesses)
        game.initialize(word=game.secret, reinitialize=True)
        game.start_time = datetime.datetime.fromtimestamp(dt.get("start_time"))
        return game

    def end_game(self):
        self.end_time = datetime.datetime.now()

    def stats(self):
        time = (self.end_time or datetime.datetime.now()) - self.start_time
        return {
            "guesses": len(self.guesses) - 1,
            "all_guesses": len(self.all_guesses) - 1,
            "time": time.days * 86400 + time.seconds
        }

    def guess(self, message):
        word = message.lower().strip()
        datum = self.top5000.get(word, None)
        if word == self.secret:
            self.guesses.add(word)
            self.all_guesses.add(word)
            self.end_game()
            return True
        elif datum:
            self.guesses.add(word)
            self.all_guesses.add(word)
            return datum
        elif word in allowed_words_set:
            self.all_guesses.add(word)
        return None

    def initialize(self, word=None, reinitialize=False):
        if word:
            if not word in valid_words_set:
                return f'Word {word} is not valid; game will not begin'
            secret_word = word
        else:
            secret_word = random.choice(valid_words_list)

        try:
            data = json.load(open(f'words/{secret_word}.json'))
        except Exception as e:
            return f'Server Error: Failed to Start Game'

        self.secret = data["word"]

        top5000 = {}
        cws = None
        for word_info in data["top_words"]:
            ws = WordScore(idx=word_info["n"], score=word_info["score"], word=word_info["word"])
            if ws.word in common_words_set:
                cws = ws
            top5000[word_info["word"]] = ws

        if cws is not None:
            ws = cws

        self.guesses.add(ws.word)
        self.all_guesses.add(ws.word)
        self.top5000 = top5000

        print("New game with secret:", secret_word)
        if not reinitialize:
            self.start_time = datetime.datetime.now()
        return f'A new game has started.\nYour starting hint is: {ws.format()}.'


class Aggregate:
    def __init__(self, guesses=0, all_guesses=0, time=0, n=0):
        self.guesses = guesses
        self.all_guesses = all_guesses
        self.time = time
        self.n = n

    def add_stats(self, game_stats):
        self.guesses += game_stats.get("guesses", 0)
        self.all_guesses += game_stats.get("all_guesses", 0)
        self.time += game_stats.get("time", 0)
        self.n += 1

    def to_string(self):
        return f'Aggregate Stats:\nTotal Games: **{self.n}**\nTotal Guesses: **{self.all_guesses}** *({round(self.all_guesses/self.n, 2)})*\nTotal Top5000: **{self.guesses}** *({round(self.guesses/self.n, 2)})*\nTotal Accuracy: **{round(self.guesses/self.all_guesses * 100, 2)}%**\nTotal Time: **{get_duration_string(self.time)}** *({get_duration_string(self.time/self.n)})*'

    @classmethod
    def from_dict(cls, dt):
        return cls(
            guesses=dt.get("guesses", 0), 
            all_guesses=dt.get("all_guesses", 0),
            time=dt.get("time", 0),
            n=dt.get("n", 0)
        )
    
    def to_dict(self):
        return {
            "guesses": self.guesses,
            "all_guesses": self.all_guesses,
            "time": self.time,
            "n": self.n
        }

class ChannelGame:
    def __init__(self, game=None):
        self.game = game 
        self.channel = None
        self.history = []
        self.agg = Aggregate()

    def to_dict(self):
        game_dt = None
        if self.game:
            game_dt = self.game.to_dict()
        return {
            "game": game_dt,
            "history": self.history,
            "agg": self.agg.to_dict(),
            "channel_id": self.channel.id
        }

    @classmethod
    async def from_dict(cls, channel_id, dt):
        game_dt = dt.get("game")
        game = None
        if game_dt:
            game = Game.from_dict(game_dt)
        val = cls(game=game)
        await val.set_channel(channel_id=channel_id)
        val.history = dt.get("history") or []
        agg = dt.get("agg")
        if agg:
            val.agg = Aggregate.from_dict(agg)
        return val
        
    async def set_channel(self, channel_id):
        if self.channel is not None:
            return
        self.channel = await client.fetch_channel(channel_id)

    async def guess(self, message, author):
        result = self.game.guess(message)
        if result is True:
            await self.end_game(won=True, author=author)
        elif result is None:
            return
        else:
            await self.channel.send(result.format_find())

    async def provide_top(self):
        top5000 = self.game.top5000
        guesses = self.game.guesses
        best = [top5000.get(w) for w in guesses]
        best.sort(key=lambda x : x.idx)
        msges = ["Top words:"]
        for i, ws in enumerate(best):
            msges.append(ws.format())
            if i >= 20:
                break
        await self.channel.send("\n".join(msges))

    async def aggregate(self):
        await self.channel.send(self.agg.to_string())

    async def provide_history(self):
        while len(self.history) > 7:
            del self.history[0]
        msgs = []
        for h in self.history:
            msg = self.stringify_game_stats(h)
            msg = f'Secret: `{h["secret"]}`\n{msg}'
            author = h.get("author")
            if author:
                msg = f'Winner: {author}\n{msg}'
            msgs.append(msg)
        await self.channel.send('\n-----\n'.join(msgs))

    async def start_game(self, message_string):
        if self.game:
            await self.channel.send("There is a game still in progress")
        else:
            message_split = [i for i in message_string.split(' ') if i]
            if len(message_split) > 1:
                word = message_split[1]
            else:
                word = None

            self.game = Game()
            response = self.game.initialize(word=word)
            # add the initial game information
            await self.channel.send(response)


    async def end_game(self, author, won=False):
        this_secret = self.game.secret
        top5000 = self.game.top5000

        game_stats = self.game.stats()
        game_stats["secret"] = this_secret
        game_stats["author"] = author
        self.history.append(game_stats)
        self.agg.add_stats(game_stats)
        while len(self.history) > 7:
            del self.history[0]

        phrases = []
        if won:
            phrases.append(f"You won! The secret word was `{this_secret}`.")
        else:
            phrases.append(f"The game ended. The secret word was `{this_secret}`.")

        phrases.append("Other words in the top 20:")
        words = []
        for w, ws in top5000.items():
            if ws.idx < 20:
                words.append(ws)
        words.sort(key=lambda x : x.idx)
        for ws in words:
            phrases.append(ws.format())
        phrases.append(self.get_stats())
        await self.channel.send("\n".join(phrases))
        self.game = None


    async def provide_stats(self):
        stats = self.get_stats()
        await self.channel.send(stats)

    async def help(self):
        helpstr = 'Commands:\n - $start | Start a new game if there isn\'t one being played\n - $top   | Show your best guesses\n - $end   | Give up and lose\n - $stats | Show the current game stats\n - $hist  | Show the last 20 games\' information\n - $agg   | Summarize the entire history'
        await self.channel.send(helpstr)

    def get_stats(self):
        stats = self.game.stats()
        return self.stringify_game_stats(stats)

    def stringify_game_stats(self, stats):
        time = stats.get("time")
        guesses = stats.get("guesses")
        all_guesses = stats.get("all_guesses")

        duration_string = get_duration_string(time)
        return f'Total guesses: {all_guesses}\nTop 5000 Discovered: {guesses}\nDuration: {duration_string}'


def get_duration_string(seconds):
    seconds = int(seconds)
    days = seconds // 86400
    total_seconds = seconds % 86400
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    duration_string = ''
    if seconds:
        duration_string = f' {seconds} seconds'
    if minutes:
        duration_string = f' {minutes} minutes{duration_string}'
    if hours:
        duration_string = f' {hours} hours{duration_string}'
    if days:
        duration_string = f' {days} days{duration_string}'
    duration_string = duration_string.strip()
    return duration_string



class Semanti(disnake.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.games = dict() 
        self.history = dict()
        self.last_save = datetime.datetime.now()
        self.savefile = 'save.json'
        self.ready = False

    async def on_ready(self):
        try:
            if os.path.exists(self.savefile):
                with open(self.savefile, 'r') as ifs:
                    savefile = json.load(ifs)
                    games = savefile['games']
                    for dt in games:
                        channel_id = dt["channel_id"]
                        self.games[channel_id] = await ChannelGame.from_dict(channel_id=channel_id, dt=dt)
            print("Loaded state")
        except Exception as e:
            print(f"Failed to read the savefile: {e}")
        self.ready = True   

    async def on_message(self, message):
        if not self.ready:
            return

        if message.channel.name.lower() != 'semanti':
            return

        channel_id = message.channel.id
        if channel_id in self.games:
            game = self.games.get(channel_id)
        else:
            game = ChannelGame()
            await game.set_channel(channel_id=channel_id) 
            self.games[channel_id] = game

        message_content = message.content

        if message_content.startswith("$start"):
            await game.start_game(message_content)
        elif message_content in ["$help"]:
            await game.help()
        elif message_content == "$agg":
            await game.aggregate()
        elif message_content == "$hist":
            await game.provide_history()
        elif game.game is None:
            return  # no game no play
        elif message_content == "$end":
            await game.end_game(won=False, author="YOU GAVE UP")
        elif message_content == "$top":
            await game.provide_top()
        elif message_content == "$stats":
            await game.provide_stats()
        else:
            await game.guess(message_content, message.author.name)

        if datetime.datetime.now() - self.last_save >  datetime.timedelta(seconds=3):
            self.save_game()
    
    def save_game(self):
        if not self.games:
            return
        self.last_save = datetime.datetime.now()
        try:
            if os.path.exists(self.savefile):
                with open(self.savefile, 'r') as ifs:
                    data = json.load(ifs)
                if data.get("games"):
                    with open(f'{self.savefile}.bak', 'w') as ofs:
                        ofs.write(json.dumps(data))
                        ofs.close()

            save_dict = dict()
            save_dict["games"] = list()
            game_saves = save_dict["games"]
            games = self.games
            for k, v in games.items():
                game_save_dt = v.to_dict()
                game_saves.append(game_save_dt)
            if game_saves:
                with open(self.savefile, 'w') as ofs:
                    ofs.write(json.dumps(save_dict))
                    ofs.close()
        except Exception as e:
            print(f'Failed to save the game: {e}')


client = Semanti()
client.run(BOT_TOKEN)
