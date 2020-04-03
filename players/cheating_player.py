"""A smart cheating Hanabi player.

Tries to make intelligent moves when looking at his own cards.  The following
table gives the approximate percentages of this strategy reaching maximum score
(over 10000 games, at seed 0).

Players | 5 suits | 6 suits | black |
--------|---------|---------|-------|
   2    |   95.0  |   90.4  | 67.9  |
   3    |   98.5  |   98.4  | 80.2  |
   4    |   98.1  |   98.3  | 77.3  |
   5    |   97.1  |   97.9  | 73.7  |

Average number of points lost (either 25 or 30 minus average score attained):
Players | 5 suits | 6 suits | black |
--------|---------|---------|-------|
   2    |  0.070  |  0.159  | 0.735 |
   3    |  0.019  |  0.020  | 0.401 |
   4    |  0.023  |  0.022  | 0.460 |
   5    |  0.036  |  0.026  | 0.501 |

Possible improvements (probably this doesn't actually increase the win percentage):
- When playing a card, prefer one that allows other players to follow up in the
  same suit
- When discarding a card you see in someone else's hand: don't do this if the
  other player has a lot of playable cards
- When discarding the first copy of a card, prefer suits with low progress
- If I can play, but someone else has the same card, and they don't have a critical 4
  (or 5 above it), let them play it

To appreciate the difficulty in writing a good cheating player, the following statements are all FALSE:
- if you have a playable card, you always want to play a card
- if you have a playable card, you never want to discard
- if you have a playable card and 7 clues, you never want to discard
- if you have a playable 4, and the player with a playable 5 has no other playable cards, you always want to play your 4.
- if you want to play, you always want to play a card with the lowest value
- if you want to play, you always want to play a card with the lowest value or a 5
- if you have a playable yellow 3 and playable blue 4, and someone else has the blue 4, but no other useful cards, then you never want to play your blue 4.
- when there are no cards in the deck left it doesn't matter which of your playable cards you play
- if the players collectively have at least one copy of each card that still needs to be played, you never want to discard if you have a clue
- it never hurts to discard a card that you see in another player's hand
- in the early game (when no player has discarded yet), if multiple players have useless cards in their hands, it doesn't matter who of them discards first
- you never want to intentionally misplay

["you always want to do X" is defined to mean that there is no situation where doing an action other than X is *guaranteed* better than performing X (in that situation)]
["you never want to do X" is defined to mean that there is no situation where doing action X is *guaranteed* better than performing any other action (in that situation)]
[this cheating bot does make some of those mistakes, though]
"""

from hanabi_classes import *
from bot_utils import *

def a_copy_of_all_useful_cards_is_drawn(r):
    """Returns True if a copy of every useful card is in the hand of all players, including me"""
    return is_subset(get_all_useful_cardnames(r), names(get_all_cards(r)))

def all_useful_cards_are_drawn(r):
    """Returns True if all copies of every useful card are in the hand of some player, including me
    (or in the discard pile)"""
    return not [card for card in get_all_useful_cardnames(r) if\
      r.discardpile.count(card) + names(get_all_cards(r)).count(card) < number_of_copies(card)]

class CheatingPlayer(AIPlayer):

    @classmethod
    def get_name(cls):
        return 'cheater'

    def give_a_hint(self, me, r):
        """Clue number to the newest card of the next player"""
        target = next(me,r)
        return 'hint', (target, r.h[target].cards[-1]['name'][0])

    def want_to_discard(self, cards, player, r, progress):
        """Returns a pair (badness, card) where badness indicates how bad it is
        to discard one of the cards for player and card is the least bad option.
        badness = 1: discard useless card
        badness = 3-6: discard card which is already in some else's hand
        (depends on the number of players)
        badness between 20 and 40: discard the first copy of a non-5 card
        (4s are badness 20, 3s badness 30, 2s badness 40)
        badness >= 100: discard a necessary card
        Add 6 badness if I have a critical 4 or a 5 above a critical 4 in 2 player games."""

        base_badness = 0
        # With 2 players we can fine-tune the discards a bit more: if I have a critical 4 or a 5 above a critical 4, I prefer not to discard.
        if r.nPlayers == 2:
            critical_fours = [suit for suit in r.suits if is_critical('4' + suit, r)]
            if critical_fours and [card for card in cards if card['name'][1] in critical_fours and 4 <= int(card['name'][0]) <= 5]:
                base_badness = 6

        discardCards = get_played_cards(cards, progress)
        if discardCards: # discard a card which is already played
            return 1 + base_badness, discardCards[0]
        discardCards = get_duplicate_cards(cards)
        if discardCards: # discard a card which occurs twice in your hand
            return 1 + base_badness, discardCards[0]
        discardCards = get_visible_cards(cards, get_all_visible_cards(player, r))
        if discardCards: # discard a card which you can see (lowest first).
                         # Empirically this is slightly worse with fewer players
            return 8 - r.nPlayers + base_badness, find_lowest(discardCards)
        discardCards = [card for card in cards if not is_critical(card['name'], r)]
        if discardCards: # discard a card which is not unsafe to discard
            card = find_highest(discardCards)
            return 60 - 10 * int(card['name'][0]) + base_badness, card
        cards_copy = list(cards)
        card = find_highest(cards_copy) # discard a critical card
        return 600 - 100 * int(card['name'][0]), card

    def play(self, r):
        me = r.whoseTurn
        cards = r.h[me].cards
        progress = r.progress

        # determine whether the game is in the endgame
        # (this can cause the player to clue instead of discard)
        endgame = count_unplayed_playable_cards(r, progress) - len(r.deck)
        # number of allowed discards
        allowable_discards = len([pl for pl in range(r.nPlayers) if get_usefuls(r.h[pl].cards, progress)]) - endgame

        playableCards = get_plays(cards, progress)
        usefulCards = get_usefuls(cards, progress)
        badness, my_discard = self.want_to_discard(cards, me, r, progress)

        # stop if we can (probably) improve the score of this game (for debugging)
        # if r.gameOverTimer == 0 and sum(progress.values()) + int(bool(playableCards)) < len(r.suits) * 5:
        #     if cards[-1]['name'][1] != BLACK_SUIT or sum(progress.values()) + 6 - int(cards[-1]['name'][0]) < len(r.suits) * 5:
        #         r.debug['stop'] = 0

        # todo: if there are 0/1 hints and another player has only critical (or very useful) cards, consider discarding.

        if playableCards: # If I have a playable card, almost always play this card.
            playableCards.reverse() # play newest cards first
            # sometimes I don't want to play in the endgame
            if endgame > 0 and r.gameOverTimer is None and r.hints:
                # If I only have one 5 and all the useful cards are drawn, don't play it yet.
                # in *very* rare cases I might even need to discard in this case (not implemented).
                if len(usefulCards) == 1 and all_useful_cards_are_drawn(r):
                    if int(playableCards[0]['name'][0]) == 5:
                        return self.give_a_hint(me, r)
                    # also stall with a 4, if the player with a 5 has another critical card to play
                    if int(playableCards[0]['name'][0]) == 4:
                        suit = playableCards[0]['name'][1]
                        players_with_5 = [pl for pl in range(r.nPlayers) if '5' + suit in names(r.h[pl].cards)]
                        # note: this list can be empty if the 5 is already discarded
                        if (not players_with_5) or [card for card in r.h[players_with_5[0]].cards if\
                            is_playable(card, progress) and is_critical(card['name'], r)]:
                            return self.give_a_hint(me, r)
                # If I have only one useful card, the deck has 1 card, and someone else has 2 critical cards (at least one of which playable), don't play
                if len(r.deck) == 1 and len(usefulCards) == 1 and \
                    [pl for pl in other_players(me, r)[0:r.hints] if len(get_criticals(r.h[pl].cards, r)) >= 2 and get_plays(r.h[pl].cards, progress)]:
                    return self.give_a_hint(me, r)
                # if I have only 1 playable card, which is a 4, and at least one other useful card, and
                # someone else who has only 1 useful cards can play my playable, I let them do it.
                if len(playableCards) == 1 and len(usefulCards) > 1:
                    playable = playableCards[0]['name']
                    players_with_4 = [pl for pl in range(r.nPlayers) if playable in names(r.h[pl].cards)]
                    if playable[0] == '4' and players_with_4 and\
                      len(get_usefuls(r.h[players_with_4[0]].cards, progress)) == 1:
                        players_with_5 = [pl for pl in range(r.nPlayers) if '5' + playable[1] in names(r.h[pl].cards)]
                        if not (players_with_5 and is_between(players_with_5[0], next(me, r), players_with_4[0])):
                            return self.give_a_hint(me, r)
                        # Exceptions:
                        # * The player with the 5 currently has no plays, and has at least 2 useful cards
                        # * The player with the 5 will not have a another turn to play the 5 if I don't play now
                        if not ((not get_plays(r.h[players_with_5[0]].cards, progress) and len(get_usefuls(r.h[players_with_5[0]].cards, progress)) >= 2) or\
                          len(r.deck) <= len([pl for pl in range(r.nPlayers) if is_between(pl, next(me, r), players_with_5[0]) and get_plays(r.h[pl].cards, progress)])):
                            return self.give_a_hint(me, r)

            # I prefer to play 5s over playable 4s for which I have the 5 in hand
            if len(playableCards) >= 2 and [card for card in playableCards if card['name'][0] == '5']:
                playableCards = [card for card in playableCards if not (card['name'][0] == '4' and
                '5' + card['name'][1] in names(cards))]

            # We want to first play the lowest card in our hand, and when tied, play a critical card.
            # There are two exceptions:
              # In the last round of the game, we always want to play critical cards first (otherwise we definitely lose)
              # In the penultimate round of the game, if we have at least two critical cards, we want to play one of those.
                # We use a sloppy way of checking whether this is the penultimate round,
                # by checking if the deck is smaller than the number of players with a playable card.
            if r.gameOverTimer is None and\
            not (len(r.deck) <= len([pl for pl in range(r.nPlayers) if get_plays(r.h[pl].cards, progress)]) and\
                len(get_criticals(cards, r)) >= 2):
                playableCards = find_all_lowest(playableCards, lambda card: int(card['name'][0]))
                playableCards = find_all_highest(playableCards, lambda card: int(is_critical(card['name'], r)))
            else:
                playableCards = find_all_highest(playableCards, lambda card: int(is_critical(card['name'], r)))
                playableCards = find_all_lowest(playableCards, lambda card: int(card['name'][0]))
            visiblecards = names(get_all_visible_cards(me, r))
            # prefer to play cards that are not visible in other hands
            playableCards = find_all_lowest(playableCards, lambda card: int(card['name'] in visiblecards))
            return 'play', playableCards[0]

        if r.hints == 8: # Hint if you are at maximum hints
            return self.give_a_hint(me, r)

        if not r.hints: # Discard at 0 hints.
            return 'discard', my_discard

        # if there are only 2 cards in the deck and we are waiting for a 3 (or lower), then the player with the one away card (4 or lower) cannot discard.
        if len(r.deck) == 2 and r.hints >= r.nPlayers - 1:
            suits = [suit for suit in r.suits if r.progress[suit] <= 2 and str(r.progress[suit] + 1) + suit not in get_all_cards(r)]
            if len(suits) == 1:
                suit = suits[0]
                next_value = r.progress[suit] + 1
                players_with_two_away = [pl for pl in range(r.nPlayers) if str(next_value + 2) + suit in names(r.h[pl].cards)]
                players_with_one_away = [pl for pl in range(r.nPlayers) if str(next_value + 1) + suit in names(r.h[pl].cards)]
                # if players_with_one_away: # this doesn't work, there could be more than one player with a one-away card
                #     if players_with_one_away[0] == me:
                #         return self.give_a_hint(me, r)
                #     if players_with_one_away[0] == next(me, r) or r.hints == r.nPlayers - 1:
                #         return 'discard', my_discard
                # If the 2-away card is not yet drawn, then anybody can discard, as long as they are not the only one with the one away card.
                if not players_with_two_away and [pl for pl in players_with_one_away if pl != me] and\
                    sum(progress.values()) == (len(r.suits) - 1) * 5 + r.progress[suit]:
                    return 'discard', my_discard
                if len(players_with_two_away) == 1:
                    player_with_two_away = players_with_two_away[0]
                    if [pl for pl in players_with_one_away if is_between(me, player_with_two_away, pl)] and\
                        (me != player_with_two_away or sum(progress.values()) == (len(r.suits) - 1) * 5 + r.progress[suit]):
                        return 'discard', my_discard
                    else:
                        return self.give_a_hint(me, r)

                # if players_with_two_away:
                #     player_with_two_away = players_with_two_away[0]
                #     if [pl for pl in players_with_one_away if is_between(me, player_with_two_away, pl)] and\
                #         (me != player_with_two_away or sum(progress.values()) == 27):
                #         return 'discard', my_discard
                #     else:
                #         return self.give_a_hint(me, r)

        # hint if the next player has no useful card, but I do, and could draw another one, and there are enough clues
        if r.hints >= 8 - len(usefulCards) and not all_useful_cards_are_drawn(r) and\
          not get_usefuls(r.h[next(me, r)].cards, progress):
            return self.give_a_hint(me, r)

        if endgame > 0:
            # don't draw the last card by discarding too early
            if len(r.deck) == 1:
                return self.give_a_hint(me, r)

            # todo: in 5 (and 4?) player games, if only 1 card can be played in the next round, discard under some conditions (necessary: len(r.deck) >= 2)
            # even better: count ahead, and if you know someone has to discard at some point, prefer to discard now.

            # hint if someone can play, unless you are waiting for a low card still to be drawn
            useful = get_all_useful_cardnames(r)
            undrawn = [int(name[0]) for name in useful if name not in names(get_all_cards(r))]

            # if there is only 1 player with a playable card, prefer to discard
            want_to_discard = False #allowable_discards and len([pl for pl in range(r.nPlayers) if get_plays(r.h[pl].cards, progress)]) == 1

            # In 5 player games, we might want to discard more aggressively if we are still waiting for a low card
            # (compared over 10000 games in vanilla/rainbow on seeds 0-3)
            waiting_for_low_card = r.nPlayers == 5 and undrawn and endgame < r.nPlayers - min(undrawn)
            if not waiting_for_low_card and not want_to_discard:
                for i in other_players(me, r)[0:r.hints]:
                    if get_plays(r.h[i].cards, progress):
                        return self.give_a_hint(me, r)

        # Discard if you can safely discard or if you have no hints.

        if r.hints + badness < 10 or r.hints == 0:
            return 'discard', my_discard
        other_badness = []
        for i in other_players(me, r)[0:r.hints]:
            if get_plays(r.h[i].cards, progress):
                other_badness.append(0)
            else:
                other_badness.append(self.want_to_discard(r.h[i].cards, i, r, progress)[0])

        # If someone can play or discard more safely before you run out of
        # hints, give a hint.
        #
        if min(other_badness) < badness:
            return self.give_a_hint(me, r)
        # discard the highest useful card
        return 'discard', my_discard
