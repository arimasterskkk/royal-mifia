#!/usr/bin/env python3.5
# -*- coding: utf-8 -*-
import pickle

from telegram.ext import Updater, CommandHandler
from telegram import ParseMode
import filemanager
import random
import strings as s
import logging.config
from raven.handlers.logging import SentryHandler

sentrykey = filemanager.readfile("sentrykey.txt")

handler = SentryHandler(
    sentrykey)
logging.config.dictConfig({
    'version': 1,
    'disable_existing_loggers': True,

    'formatters': {
        'console': {
            'format': '[%(asctime)s][%(levelname)s] %(name)s '
                      '%(filename)s:%(funcName)s:%(lineno)d | %(message)s',
            'datefmt': '%H:%M:%S',
            },
        },

    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'console'
            },
        'sentry': {
            'level': 'WARNING',
            'class': 'raven.handlers.logging.SentryHandler',
            'dsn': sentrykey,
            },
        },

    'loggers': {
        '': {
            'handlers': ['console', 'sentry'],
            'level': 'DEBUG',
            'propagate': False,
            },
        'your_app': {
            'level': 'DEBUG',
            'propagate': True,
        },
    }
})

token = filemanager.readfile('telegramapi.txt')
updater = Updater(token)

freenames = s.names_list.copy()


# Ruoli possibili per i giocatori
# Base di un ruolo
class Role:
    """Classe base di un ruolo. Da qui si sviluppano tutti gli altri ruoli."""
    icon = "-"  # Icona del ruolo, da visualizzare di fianco al nome
    team = 'None'  # Squadra: 'None', 'Good', 'Evil'
    name = "UNDEFINED"  # Nome del ruolo, viene visualizzato dall'investigatore e durante l'assegnazione
    powerdesc = None  # Ha un potere? Se sì, inviagli le info su come usarlo.

    def __repr__(self) -> str:
        r = "<undefined Role>"
        return r

    def power(self, bot, game, player, arg):
        """Il potere del ruolo. Si attiva quando il bot riceve un /power in chat privata."""
        pass

    def onendday(self, bot, game):
        """Metodo chiamato alla fine di ogni giorno."""
        pass

    def ondeath(self, bot, game):
        """Metodo chiamato alla morte del giocatore."""
        pass


class Royal(Role):
    """Un membro della Royal Games. Il ruolo principale, non ha alcun potere se non quello di votare."""
    icon = s.royal_icon
    team = 'Good'
    name = s.royal_name

    def __init__(self):
        super().__init__()

    def __repr__(self) -> str:
        r = "<Role: Royal>"
        return r


class Mifioso(Role):
    """Il nemico globale. Può impostare come bersaglio una persona al giorno, per poi ucciderla alla fine."""
    icon = s.mifia_icon
    team = 'Evil'
    name = s.mifia_name
    powerdesc = s.mifia_power_description

    def __init__(self):
        super().__init__()
        self.target = None

    def __repr__(self) -> str:
        if self.target is None:
            r = "<Role: Mifioso>"
        else:
            r = "<Role: Mifioso, targeting {target}>".format(target=self.target.tusername)
        return r

    def power(self, bot, game, player, arg):
        # Imposta una persona come bersaglio da uccidere.
        selected = game.findplayerbyusername(arg)
        if selected is not None:
            self.target = selected
            player.message(bot, s.mifia_target_selected.format(target=self.target.tusername))
        else:
            player.message(bot, s.error_username)

    def onendday(self, bot, game):
        if not game.votingmifia:
            # Uccidi il bersaglio se non è protetto da un Angelo.
            if self.target is not None:
                if self.target.protectedby is None:
                    self.target.kill(bot, game)
                    game.message(bot, s.mifia_target_killed.format(target=self.target.tusername,
                                                                   icon=self.target.role.icon,
                                                                   role=self.target.role.name))
                else:
                    game.message(bot, s.mifia_target_protected.format(target=self.target.tusername,
                                                                      icon=self.target.protectedby.role.icon,
                                                                      protectedby=self.target.protectedby.tusername))
                self.target = None
        else:
            self.target = None


class Investigatore(Role):
    """L'investigatore può indagare sul vero ruolo di una persona una volta al giorno."""
    icon = s.detective_icon
    team = 'Good'
    name = s.detective_name
    powerdesc = s.detective_power_description
    refillpoweruses = 1

    def __init__(self):
        super().__init__()
        self.poweruses = self.refillpoweruses

    def __repr__(self) -> str:
        r = "<Role: Investigatore, {uses} uses left>".format(uses=self.poweruses)
        return r

    def power(self, bot, game, player, arg):
        # Indaga sul vero ruolo di una persona, se sono ancora disponibili usi del potere.
        if self.poweruses > 0:
            target = game.findplayerbyusername(arg)
            if target is not None:
                self.poweruses -= 1
                player.message(bot, s.detective_discovery.format(target=target.tusername,
                                                                 icon=target.role.icon,
                                                                 role=target.role.name,
                                                                 left=self.poweruses))
            else:
                player.message(bot, s.error_username)
        else:
            player.message(bot, s.error_no_uses)

    def onendday(self, bot, game):
        # Ripristina il potere
        self.poweruses = self.refillpoweruses


class Angelo(Role):
    """L'angelo può proteggere una persona al giorno dalla Mifia.
       Se ha successo nella protezione, il suo ruolo sarà rivelato a tutti."""
    icon = s.angel_icon
    team = 'Good'  # Squadra: 'None', 'Good', 'Evil'
    name = s.angel_name
    powerdesc = s.angel_power_description

    def __init__(self):
        super().__init__()
        self.protecting = None  # La persona che questo angelo sta proteggendo

    def __repr__(self) -> str:
        if self.protecting is None:
            r = "<Role: Angelo>"
        else:
            r = "<Role: Angelo, protecting {target}>".format(target=self.protecting.tusername)
        return r

    def power(self, bot, game, player, arg):
        # Imposta qualcuno come protetto
        selected = game.findplayerbyusername(arg)
        if selected is not None:
            if selected is not Player:
                # Togli la protezione a quello che stavi proteggendo prima
                if self.protecting is not None:
                    self.protecting.protectedby = None
                selected.protectedby = player
                self.protecting = selected
                player.message(bot, s.angel_target_selected.format(target=self.protecting.tusername))
            else:
                player.message(bot, s.error_angel_no_selfprotect)
        else:
            player.message(bot, s.error_username)

    def onendday(self, bot, game):
        # Resetta la protezione
        if self.protecting is not None:
            self.protecting.protectedby = None
        self.protecting = None


class Player:
    """Classe di un giocatore. Contiene tutti i dati riguardanti un giocatore all'interno di una partita, come il ruolo,
       e i dati riguardanti telegram, come ID e username."""
    def __init__(self, tid, tusername):
        self.tid = tid  # ID di Telegram
        self.tusername = tusername  # Username di Telegram
        self.role = Role()  # Di base, ogni giocatore è un ruolo indefinito
        self.alive = True
        self.votingfor = None  # Diventa un player se ha votato
        self.votes = 0  # Voti che sta ricevendo questo giocatore. Aggiornato da updatevotes()
        self.protectedby = None  # Protettore. Oggetto player che protegge questo giocatore dalla mifia.
        self.mifiavotes = 0  # Voti che sta ricevendo questo giocatore dalla mifia. Aggiornato da updatemifiavotes()

    def __repr__(self) -> str:
        r = "<Player {username}>".format(username=self.tusername)
        return r

    def message(self, bot, text):
        """Manda un messaggio privato al giocatore."""
        bot.sendMessage(self.tid, text, parse_mode=ParseMode.MARKDOWN)

    def kill(self, bot, game):
        """Uccidi il giocatore."""
        self.role.ondeath(bot, game)
        self.alive = False


class Game:
    """Classe di una partita, contenente parametri riguardanti stato della partita 
       e informazioni sul gruppo di Telegram."""
    def __init__(self, groupid, adminid):
        self.groupid = groupid  # ID del gruppo in cui si sta svolgendo una partita
        self.adminid = adminid  # ID telegram dell'utente che ha creato la partita con /newgame
        self.players = list()  # Lista dei giocatori in partita
        self.tokill = list()  # Giocatori che verranno uccisi all'endday
        self.phase = 'Join'  # Fase di gioco: 'Join', 'Config', 'Voting'

        self.configstep = 0  # Passo attuale di configurazione
        self.totalmifiosi = 0  # Numero di mifiosi da inserire
        self.totaldetectives = 0  # Numero di detective da inserire
        self.totalangels = 0  # Numero di angeli da inserire
        self.votingmifia = False  # Seguire le regole originali della mifia che vota?

        # Liste di ruoli in gioco, per velocizzare gli endday
        self.mifiosiingame = list()
        self.detectivesingame = list()
        self.angelsingame = list()

        # Trova un nome per la partita
        if len(freenames) > 0:
            random.shuffle(freenames)
            self.name = freenames.pop()
        else:
            self.name = str(groupid)

    def __del__(self):
        # Rimetti il nome che si è liberato in disponibili.
        try:
            int(self.name)
        except ValueError:
            freenames.append(self.name)

    def __repr__(self):
        r = "<Game {name} in group {groupid} with {nplayers} players in phase {phase}>" \
                .format(name=self.name, groupid=self.groupid, nplayers=len(self.players), phase=self.phase)
        return r

    def message(self, bot, text):
        """Manda un messaggio nel gruppo."""
        bot.sendMessage(self.groupid, text, parse_mode=ParseMode.MARKDOWN)

    def adminmessage(self, bot, text):
        """Manda un messaggio privato al creatore della partita."""
        bot.sendMessage(self.adminid, text, parse_mode=ParseMode.MARKDOWN)

    def mifiamessage(self, bot, text):
        """Manda un messaggio privato a tutti i Mifiosi nella partita."""
        # Trova tutti i mifiosi nell'elenco dei giocatori
        for player in self.players:
            if isinstance(player.role, Mifioso):
                player.message(bot, text)

    def findplayerbyid(self, tid) -> Player:
        """Trova il giocatore con un certo id."""
        for player in self.players:
            if player.tid == tid:
                return player
        else:
            return None

    def findplayerbyusername(self, tusername) -> Player:
        """Trova il giocatore con un certo username."""
        for player in self.players:
            if player.tusername.lower() == tusername.lower():
                return player
        else:
            return None

    def assignroles(self, bot):
        """Assegna ruoli casuali a tutti i giocatori."""
        random.seed()
        playersleft = self.players.copy()
        # Seleziona mifiosi
        self.mifiosiingame = random.sample(playersleft, self.totalmifiosi)
        for player in self.mifiosiingame:
            player.role = Mifioso()
            playersleft.remove(player)
        # Seleziona detective
        self.detectivesingame = random.sample(playersleft, self.totaldetectives)
        for player in self.detectivesingame:
            player.role = Investigatore()
            playersleft.remove(player)
        # Seleziona angeli
        self.angelsingame = random.sample(playersleft, self.totalangels)
        for player in self.angelsingame:
            player.role = Angelo()
            playersleft.remove(player)
        # Assegna il ruolo di Royal a tutti gli altri
        for player in playersleft:
            player.role = Royal()
        # Manda i ruoli assegnati a tutti
        for player in self.players:
            player.message(bot, s.role_assigned.format(icon=player.role.icon, name=player.role.name))
            if player.role.powerdesc is not None:
                player.message(bot, player.role.powerdesc.format(gamename=self.name))
        # Manda ai mifiosi l'elenco dei loro compagni di squadra
        text = s.mifia_team_intro
        for player in self.mifiosiingame:
            text += s.mifia_team_player.format(icon=player.role.icon, name=player.tusername)
        for player in self.mifiosiingame:
            player.message(bot, text)

    def updatevotes(self):
        """Aggiorna il conteggio dei voti di tutti i giocatori."""
        for player in self.players:
            player.votes = 0
        for player in self.players:
            if player.votingfor is not None and player.alive:
                player.votingfor.votes += 1

    def updatemifiavotes(self):
        """Aggiorna il conteggio dei voti mifiosi di tutti i giocatori."""
        for player in self.players:
            player.mifiavotes = 0
        for player in self.mifiosiingame:
            if player.alive:
                if player.role.target is not None:
                    player.role.target.mifiavotes += 1

    def mostvotedplayer(self) -> list:
        """Trova il giocatore più votato."""
        mostvoted = list()
        currenttop = 0
        self.updatevotes()
        for player in self.players:
            if player.votes > currenttop:
                mostvoted = list()
                mostvoted.append(player)
                currenttop = player.votes
            elif player.votes == currenttop:
                mostvoted.append(player)
        if currenttop > 0:
            return mostvoted
        else:
            return list()

    def mostvotedmifia(self) -> list:
        """Trova il giocatore più votato dalla mifia."""
        mostvoted = list()
        currenttop = 0
        self.updatemifiavotes()
        for player in self.players:
            if player.mifiavotes > currenttop:
                mostvoted = list()
                mostvoted.append(player)
                currenttop = player.mifiavotes
            elif player.votes == currenttop:
                    mostvoted.append(player)
        if currenttop > 0:
            return mostvoted
        else:
            return list()

    def endday(self, bot):
        """Finisci la giornata, uccidi il più votato del giorno ed esegui gli endday di tutti i giocatori."""
        # Conta i voti ed elimina il più votato.
        topvotes = self.mostvotedplayer()
        if len(topvotes) > 0:
            # In caso di pareggio, elimina un giocatore casuale.
            random.seed()
            random.shuffle(topvotes)
            lynched = topvotes.pop()
            if lynched.alive:
                self.message(bot, s.player_lynched.format(name=lynched.tusername,
                                                          icon=lynched.role.icon,
                                                          role=lynched.role.name))
                lynched.kill(bot, self)
        else:
            self.message(bot, s.no_players_lynched)
        # Fai gli endday in un certo ordine.
        # Si potrebbe fare più velocemente, credo.
        # Ma non sto ho voglia di ottimizzare ora.
        # Mifiosi
        if self.votingmifia:
            # Trova il più votato dai mifiosi e uccidilo
            killlist = self.mostvotedmifia()
            if len(killlist) > 0:
                # In caso di pareggio, elimina un giocatore casuale.
                random.seed()
                random.shuffle(killlist)
                killed = killlist.pop()
                if killed.alive:
                    if killed.protectedby is None:
                        killed.kill(bot, self)
                        self.message(bot, s.mifia_target_killed.format(target=killed.tusername,
                                                                       icon=killed.role.icon,
                                                                       role=killed.role.name))
                    else:
                        self.message(bot, s.mifia_target_protected.format(target=killed.tusername,
                                                                          icon=killed.protectedby.role.icon,
                                                                          protectedby=killed.protectedby.tusername))
        # Attiva il onendday dei mifiosi
        for player in self.mifiosiingame:
            if isinstance(player.role, Mifioso) and player.alive:
                player.role.onendday(bot, self)
        # Investigatori
        for player in self.detectivesingame:
            if isinstance(player.role, Investigatore) and player.alive:
                player.role.onendday(bot, self)
        # Angeli
        for player in self.angelsingame:
            if isinstance(player.role, Angelo) and player.alive:
                player.role.onendday(bot, self)
        # Cancella tutti i voti
        for player in self.players:
            player.votingfor = None
        # Condizioni di vittoria
        royal = 0
        mifiosi = 0
        for player in self.players:
            if player.alive and player.role.team == 'Evil':
                mifiosi += 1
            elif player.alive and player.role.team == 'Good':
                royal += 1
        if mifiosi >= royal:
            self.message(bot, s.end_mifia_outnumber + s.victory_mifia)
            for player in self.players:
                if player.role.team == 'Good':
                    player.message(bot, s.end_mifia_outnumber + s.defeat)
                elif player.role.team == 'Evil':
                    player.message(bot, s.end_mifia_outnumber + s.victory)
            self.endgame()
        elif mifiosi == 0:
            self.message(bot, s.end_mifia_killed + s.victory_royal)
            for player in self.players:
                if player.role.team == 'Good':
                    player.message(bot, s.end_mifia_killed + s.victory)
                elif player.role.team == 'Evil':
                    player.message(bot, s.end_mifia_killed + s.defeat)
            self.endgame()

    def endconfig(self, bot):
        """Fine della fase di config, inizio assegnazione ruoli"""
        self.phase = 'Voting'
        try:
            self.assignroles(bot)
        except IndexError:
            self.message(bot, s.error_not_enough_players)
            self.endgame()
        else:
            self.message(bot, s.roles_assigned_successfully)

    def endgame(self):
        inprogress.remove(self)

    def save(self):
        # Crea il file.
        try:
            file = open(str(self.groupid) + ".p", 'x')
        except FileExistsError:
            pass
        else:
            file.close()
        # Scrivi sul file.
        file = open(str(self.groupid) + ".p", 'wb')
        pickle.dump(self, file)
        file.close()

# Partite in corso
inprogress = list()


def findgamebyid(gid) -> Game:
    """Trova una partita con un certo id."""
    for game in inprogress:
        if game.groupid == gid:
            return game


def findgamebyname(name) -> Game:
    """Trova una partita con un certo nome."""
    for game in inprogress:
        if game.name.lower() == name.lower():
            return game


# Comandi a cui risponde il bot
def ping(bot, update):
    """Ping!"""
    bot.sendMessage(update.message.chat['id'], s.pong, parse_mode=ParseMode.MARKDOWN)


def newgame(bot, update):
    """Crea una nuova partita."""
    if update.message.chat['type'] != 'private':
        game = findgamebyid(update.message.chat['id'])
        if game is None:
            game = Game(update.message.chat['id'], update.message.from_user['id'])
            inprogress.append(game)
            game.message(bot, s.new_game.format(groupid=game.groupid, name=game.name))
        else:
            bot.sendMessage(update.message.chat['id'], s.error_game_in_progress, parse_mode=ParseMode.MARKDOWN)
    else:
        bot.sendMessage(update.message.chat['id'], s.error_chat_type, parse_mode=ParseMode.MARKDOWN)


def join(bot, update):
    """Unisciti a una partita."""
    game = findgamebyid(update.message.chat['id'])
    if game is not None:
        if game.phase == 'Join':
            p = game.findplayerbyid(update.message.from_user['id'])
            if p is None:
                p = Player(update.message.from_user['id'], update.message.from_user['username'])
                game.players.append(p)
                game.message(bot, s.player_joined.format(name=p.tusername))
            else:
                game.message(bot, s.error_player_already_joined)
        else:
            game.message(bot, s.error_join_phase_ended)
    else:
        bot.sendMessage(update.message.chat['id'], s.error_no_games_found, parse_mode=ParseMode.MARKDOWN)


def status(bot, update):
    """Visualizza lo stato della partita."""
    game = findgamebyid(update.message.chat['id'])
    if game is not None:
        text = s.status_header.format(name=game.name, admin=game.adminid, phase=game.phase)
        game.updatevotes()
        # Aggiungi l'elenco dei giocatori
        for player in game.players:
            if not player.alive:
                text += s.status_dead_player.format(name=player.tusername)
            else:
                text += s.status_alive_player.format(icon="\U0001F610",
                                                     name=player.tusername,
                                                     votes=str(player.votes))
        game.message(bot, text)
    else:
        bot.sendMessage(update.message.chat['id'], s.error_no_games_found, parse_mode=ParseMode.MARKDOWN)


def endjoin(bot, update):
    """Termina la fase di join e inizia quella di votazione."""
    game = findgamebyid(update.message.chat['id'])
    if game is not None and game.phase == 'Join':
        if update.message.from_user['id'] == game.adminid:
            # Inizio fase di configurazione
            game.phase = 'Config'
            game.message(bot, s.join_phase_ended)
            game.message(bot, s.config_list[0])
        else:
            game.message(bot, s.error_not_admin)
    else:
        bot.sendMessage(update.message.chat['id'], s.error_no_games_found, parse_mode=ParseMode.MARKDOWN)


def config(bot, update):
    """Configura il parametro richiesto."""
    game = findgamebyid(update.message.chat['id'])
    if game is not None and game.phase is 'Config':
        if update.message.from_user['id'] == game.adminid:
            cmd = update.message.text.split(' ', 1)
            if len(cmd) >= 2:
                if game.configstep == 0:
                    try:
                        game.totalmifiosi = int(cmd[1])
                    except ValueError:
                        game.message(bot, s.error_invalid_config)
                    else:
                        game.configstep += 1
                        game.message(bot, s.config_list[game.configstep])
                elif game.configstep == 1:
                    try:
                        game.totaldetectives = int(cmd[1])
                    except ValueError:
                        game.message(bot, s.error_invalid_config)
                    else:
                        game.configstep += 1
                        game.message(bot, s.config_list[game.configstep])
                elif game.configstep == 2:
                    try:
                        game.totalangels = int(cmd[1])
                    except ValueError:
                        game.message(bot, s.error_invalid_config)
                    else:
                        game.configstep += 1
                        game.message(bot, s.config_list[game.configstep])
                elif game.configstep == 3:
                    if cmd[1].lower() == 'testa':
                        game.votingmifia = False
                        game.endconfig(bot)
                    elif cmd[1].lower() == 'unica':
                        game.votingmifia = True
                        game.endconfig(bot)
                    else:
                        game.message(bot, s.error_invalid_config)
            else:
                game.message(bot, s.config_list[game.configstep])
        else:
            game.message(bot, s.error_not_admin)
    else:
        game.message(bot, s.error_no_games_found)


def vote(bot, update):
    """Vota per uccidere una persona."""
    game = findgamebyid(update.message.chat['id'])
    if game is not None and game.phase is 'Voting':
        player = game.findplayerbyid(update.message.from_user['id'])
        if player is not None:
            if player.alive:
                target = game.findplayerbyusername(update.message.text.split(' ')[1])
                if target is not None:
                    player.votingfor = target
                    game.message(bot, s.vote.format(voted=target.tusername))
                else:
                    game.message(bot, s.error_username)
            else:
                game.message(bot, s.error_dead)
        else:
            game.message(bot, s.error_not_in_game)
    else:
        bot.sendMessage(update.message.chat['id'], s.error_no_games_found, parse_mode=ParseMode.MARKDOWN)


def endday(bot, update):
    """Termina la giornata attuale."""
    game = findgamebyid(update.message.chat['id'])
    if game is not None and game.phase is 'Voting' and update.message.from_user['id'] == game.adminid:
        game.endday(bot)


def power(bot, update):
    """Attiva il potere del tuo ruolo."""
    if update.message.chat['type'] == 'private':
        cmd = update.message.text.split(' ', 2)
        game = findgamebyname(cmd[1])
        # Se non lo trovi con il nome, prova con l'id
        if game is None:
            game = findgamebyid(int(cmd[1]))
        if game is not None:
            player = game.findplayerbyid(int(update.message.from_user['id']))
            if player is not None:
                if player.alive:
                    player.role.power(bot, game, player, cmd[2])
                else:
                    player.message(bot, s.error_dead)
            else:
                bot.sendMessage(update.message.chat['id'], s.error_not_in_game, parse_mode=ParseMode.MARKDOWN)
        else:
            bot.sendMessage(update.message.chat['id'], s.error_no_games_found, parse_mode=ParseMode.MARKDOWN)
    else:
        bot.sendMessage(update.message.chat['id'], s.error_private_required, parse_mode=ParseMode.MARKDOWN)


def role(bot, update):
    """Visualizza il tuo ruolo."""
    game = findgamebyid(update.message.chat['id'])
    if game is not None and game.phase is 'Voting':
        player = game.findplayerbyid(update.message.from_user['id'])
        if player is not None:
            if player.alive:
                player.message(bot, s.role_assigned.format(icon=player.role.icon, name=player.role.name))
                game.message(bot, s.check_private)
            else:
                game.message(bot, s.error_dead)
        else:
            bot.sendMessage(update.message.chat['id'], s.error_not_in_game, parse_mode=ParseMode.MARKDOWN)
    else:
        bot.sendMessage(update.message.chat['id'], s.error_no_games_found, parse_mode=ParseMode.MARKDOWN)


def kill(bot, update):
    """Uccidi un giocatore in partita."""
    if __debug__:
        game = findgamebyid(update.message.chat['id'])
        if game is not None and game.phase is 'Voting':
            if update.message.from_user['id'] == game.adminid:
                target = game.findplayerbyusername(update.message.text.split(' ')[1])
                if target is not None:
                    target.kill(bot, game)
                    game.message(bot, s.admin_killed.format(name=target.tusername,
                                                            icon=target.role.icon,
                                                            role=target.role.name))
                else:
                    game.message(bot, s.error_username)
            else:
                game.message(bot, s.error_not_admin)
        else:
            bot.sendMessage(update.message.chat['id'], s.error_no_games_found, parse_mode=ParseMode.MARKDOWN)


def delete(bot, update):
    """Elimina una partita in corso."""
    if update.message.chat['type'] == 'private':
        if update.message.from_user['username'] == "Steffo":
            cmd = update.message.text.split(' ', 2)
            game = findgamebyname(cmd[1])
            # Se non lo trovi con il nome, prova con l'id
            if game is None:
                game = findgamebyid(int(cmd[1]))
            if game is not None:
                game.message(bot, s.owner_ended)
                game.endgame()
            else:
                game.message(bot, s.error_no_games_found)
        else:
            bot.sendMessage(update.message.chat['id'], s.error_not_owner, parse_mode=ParseMode.MARKDOWN)
    else:
        bot.sendMessage(update.message.chat['id'], s.error_chat_type, parse_mode=ParseMode.MARKDOWN)


def fakerole(bot, update):
    """Manda un finto messaggio di ruolo."""
    if update.message.chat['type'] == 'private':
        bot.sendMessage(update.message.chat['id'], s.role_assigned.format(icon=s.royal_icon, name=s.royal_name),
                        parse_mode=ParseMode.MARKDOWN)
        bot.sendMessage(update.message.chat['id'], s.role_assigned.format(icon=s.mifia_icon, name=s.mifia_name),
                        parse_mode=ParseMode.MARKDOWN)
        bot.sendMessage(update.message.chat['id'], s.role_assigned.format(icon=s.detective_icon, name=s.detective_name),
                        parse_mode=ParseMode.MARKDOWN)
        bot.sendMessage(update.message.chat['id'], s.role_assigned.format(icon=s.angel_icon, name=s.angel_name),
                        parse_mode=ParseMode.MARKDOWN)
    else:
        bot.sendMessage(update.message.chat['id'], s.error_private_required, parse_mode=ParseMode.MARKDOWN)


def load(bot, update):
    """Carica una partita salvata."""
    file = open(str(update.message.chat['id']) + ".p", "rb")
    game = pickle.load(file)
    inprogress.append(game)
    game.message(bot, s.game_loaded)


def save(bot, update):
    """Salva una partita su file."""
    game = findgamebyid(update.message.chat['id'])
    if game is not None:
        game.save()
    else:
        bot.sendMessage(update.message.chat['id'], s.error_no_games_found, parse_mode=ParseMode.MARKDOWN)


def debug(bot, update):
    """Visualizza tutti i ruoli e gli id."""
    if __debug__:
        game = findgamebyid(update.message.chat['id'])
        if game is not None:
            if game.adminid == update.message.from_user['id']:
                text = s.status_header.format(name=game.groupid, admin=game.adminid, phase=game.phase)
                game.updatevotes()
                # Aggiungi l'elenco dei giocatori
                for player in game.players:
                    if not player.alive:
                        text += s.status_dead_player.format(name=player.tusername)
                    else:
                        text += s.status_alive_player.format(icon=player.role.icon,
                                                             name=player.tusername,
                                                             votes=str(player.votes))
                game.adminmessage(bot, text)
                game.message(bot, s.check_private)
            else:
                game.message(bot, s.error_not_admin)
        else:
            bot.sendMessage(update.message.chat['id'], s.error_no_games_found, parse_mode=ParseMode.MARKDOWN)


def debuggameslist(bot, update):
    """Visualizza l'elenco delle partite in corso."""
    if __debug__:
        bot.sendMessage(update.message.from_user['id'], repr(inprogress), parse_mode=ParseMode.MARKDOWN)

updater.dispatcher.add_handler(CommandHandler('ping', ping))
updater.dispatcher.add_handler(CommandHandler('newgame', newgame))
updater.dispatcher.add_handler(CommandHandler('join', join))
updater.dispatcher.add_handler(CommandHandler('endjoin', endjoin))
updater.dispatcher.add_handler(CommandHandler('vote', vote))
updater.dispatcher.add_handler(CommandHandler('endday', endday))
updater.dispatcher.add_handler(CommandHandler('power', power))
updater.dispatcher.add_handler(CommandHandler('status', status))
updater.dispatcher.add_handler(CommandHandler('role', role))
updater.dispatcher.add_handler(CommandHandler('debug', debug))
updater.dispatcher.add_handler(CommandHandler('debuggameslist', debuggameslist))
updater.dispatcher.add_handler(CommandHandler('kill', kill))
updater.dispatcher.add_handler(CommandHandler('config', config))
updater.dispatcher.add_handler(CommandHandler('fakerole', fakerole))
updater.dispatcher.add_handler(CommandHandler('save', save))
updater.dispatcher.add_handler(CommandHandler('load', load))
updater.dispatcher.add_handler(CommandHandler('delete', delete))
updater.start_polling()
print("Bot avviato!")
if __name__ == "__main__":
    updater.idle()
