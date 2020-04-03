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
"""

from hanabi_classes import *
from bot_utils import *

def all_useful_cards_are_drawn(r):
    """Returns True if a copy of every useful card is in the hand of all players, including me"""
    return is_subset(get_all_useful_cardnames(r), names(get_all_cards(r)))

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
        card = find_highest(cards_copy)
        return 600 - 100 * int(card['name'][0]), card

    def play(self, r):
        me = r.whoseTurn
        cards = r.h[me].cards
        progress = r.progress

        # determine whether the game is in the endgame
        # (this can cause the player to clue instead of discard)
        endgame = count_unplayed_playable_cards(r, progress) - len(r.deck)

        playableCards = get_plays(cards, progress)

        # if r.gameOverTimer == 0 and sum(progress.values()) + int(bool(playableCards)) < len(r.suits) * 5:
        #     r.debug['stop'] = 0

        if playableCards: # Play a card, if possible (lowest value first)
            playableCards.reverse() # play newest cards first
            # If I only have one 5 and all the useful cards are drawn, don't play it yet
            # todo: sometimes I even want to discard in this case.
            if endgame > 0 and r.gameOverTimer is None and all_useful_cards_are_drawn(r) and\
                r.hints and len([card for card in cards if not has_been_played(card, progress)]) == 1:
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

            # I prefer to play 5s over playable 4s for which I have the 5 in hand
            if len(playableCards) >= 2 and [card for card in playableCards if card['name'][0] == '5']:
                playableCards = [card for card in playableCards if not (card['name'][0] == '4' and
                '5' + card['name'][1] in names(cards))]

            # We want to first play the lowest card in our hand, and then a critical card.
            # However, in the last round of the game, we first want to play critical cards (otherwise we definitely lose)
            # In the penultimate round of the game, we want to play critical cards if we have at least 2.
            # We use a sloppy way of checking whether this is the penultimate round,
            # by checking if the deck is smaller than the number of players with a playable card.
            if r.gameOverTimer is None and\
            not (len(r.deck) <= len([i for i in range(r.nPlayers) if get_plays(r.h[i].cards, progress)]) and\
                len([card for card in cards if is_critical(card['name'], r)]) >= 2):
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

        if endgame > 0:
            # hint if someone can play, unless you are waiting for a low card still to be drawn
            useful = get_all_useful_cardnames(r)
            undrawn = [int(name[0]) for name in useful if name not in names(get_all_cards(r))]
            # returns False if we are still waiting for a low card,
            # in which case players should discard a more aggressively
            # This seems to be good in 5 players (compared over 10000 games in vanilla/rainbow on seeds 0-3)
            not_waiting_for_low_card = (not undrawn or endgame >= r.nPlayers - min(undrawn)) or r.nPlayers != 5
            if not_waiting_for_low_card :
                for i in other_players(me, r)[0:r.hints]:
                    if get_plays(r.h[i].cards, progress):
                        return self.give_a_hint(me, r)

            # if we are waiting for a 3, let the player with the 5 draw it
            if r.hints >= r.nPlayers - 1 and len(r.deck) == 2:
                suits = [suit for suit in r.suits if r.progress[suit] == 2]
                if suits:
                    # r.debug['stop'] = 0
                    suit = suits[0]
                    players_with_5 = [i for i in range(r.nPlayers) if '5' + suit in names(r.h[i].cards)]
                    players_with_4 = [i for i in range(r.nPlayers) if '4' + suit in names(r.h[i].cards)]
                    # if the 5 is not yet drawn, then anybody can discard, as long as they are not the only one with the 4.
                    # But this will go correctly because of the remaining logic in this file
                    if players_with_5:
                        player = players_with_5[0]
                        if [pl for pl in players_with_4 if is_between(me, player, pl)] and\
                            (me != player or sum(progress.values()) == 27):
                            return 'discard', self.want_to_discard(cards, me, r, progress)[1]
                        else:
                            return self.give_a_hint(me, r)

            # hint if the next player has no useful card, but I do, and could draw another one
            if r.hints and [card for card in cards if not has_been_played(card, progress)] and\
            not [card for card in r.h[next(me, r)].cards if not has_been_played(card, progress)] and\
            not_waiting_for_low_card and not all_useful_cards_are_drawn(r):
                return self.give_a_hint(me, r)

            # don't draw the last card by discarding
            if r.hints and len(r.deck) == 1:
                return self.give_a_hint(me, r)

        # Discard if you can safely discard or if you have no hints.
        badness, discard = self.want_to_discard(cards, me, r, progress)
        if r.hints + badness < 10 or r.hints == 0:
            return 'discard', discard
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
        # discard the highest critical card
        return 'discard', discard
