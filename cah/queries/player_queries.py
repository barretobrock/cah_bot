from typing import (
    Dict,
    List,
    Optional,
    Union,
)

from loguru import logger
import pandas as pd
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql import (
    and_,
    func,
    not_,
    or_,
)

from cah.db_eng import WizzyPSQLClient
from cah.model import (
    TableAnswerCard,
    TableGameRound,
    TableHonorific,
    TablePlayer,
    TablePlayerHand,
    TablePlayerPick,
    TablePlayerRound,
)


class PlayerHandCardType:
    answer_card_key: int
    card_text: str
    player_key: int
    hand_id: int


PlayerHandType = List[PlayerHandCardType]


class PlayerQueries:
    """Storing the query methodology here for easier mocking"""

    def __init__(self, eng: WizzyPSQLClient, log: logger):
        self.eng = eng
        self.log = log.bind(child_name=self.__class__.__name__)

    def get_player_table(self, player_hash: str) -> TablePlayer:
        with self.eng.session_mgr() as session:
            tbl = session.query(TablePlayer).filter(TablePlayer.slack_user_hash == player_hash).one_or_none()
            if tbl is not None:
                session.expunge(tbl)
        return tbl

    def set_player_table_attr(self, player_hash: str, attr: InstrumentedAttribute,
                              value: Optional[Union[int, bool, str]]):
        with self.eng.session_mgr() as session:
            session.query(TablePlayer).filter(TablePlayer.slack_user_hash == player_hash).update({
                attr: value
            })

    def get_player_round_table(self, player_id: int, game_round_id: int, game_id: int) -> TablePlayer:
        with self.eng.session_mgr() as session:
            tbl = session.query(TablePlayerRound).filter(and_(
                TablePlayerRound.game_key == game_id,
                TablePlayerRound.game_round_key == game_round_id,
                TablePlayerRound.player_key == player_id
            )).one_or_none()
            if tbl is not None:
                session.expunge(tbl)
        return tbl

    def set_player_round_table(self, player_id: int, game_round_id: int, game_id: int,
                               attr: InstrumentedAttribute, value: Optional[Union[int, bool, str]]):
        with self.eng.session_mgr() as session:
            session.query(TablePlayerRound).filter(and_(
                TablePlayerRound.game_key == game_id,
                TablePlayerRound.game_round_key == game_round_id,
                TablePlayerRound.player_key == player_id
            )).update({
                attr: value
            })

    def get_total_games_played(self, player_id: int) -> int:
        with self.eng.session_mgr() as session:
            return session.query(func.count(func.distinct(TablePlayerRound.game_key))).filter(
                TablePlayerRound.player_key == player_id
            ).scalar()

    def get_honorific(self, points: int) -> str:
        with self.eng.session_mgr() as session:
            honorific: TableHonorific
            honorific = session.query(TableHonorific).filter(and_(
                    points >= TableHonorific.score_lower_lim,
                    points <= TableHonorific.score_upper_lim
                )).order_by(func.random()).limit(1).one_or_none()
            if honorific is not None:
                return honorific.text
            return 'The Unknown'

    def get_current_score(self, game_id: int, player_id: int) -> int:
        """Retrieves player's current score"""
        with self.eng.session_mgr() as session:
            return session.query(
                    func.sum(TablePlayerRound.score)
                ).filter(and_(
                    TablePlayerRound.player_key == player_id,
                    TablePlayerRound.game_key == game_id
                )).scalar()

    def get_overall_score(self, player_id: int) -> int:
        with self.eng.session_mgr() as session:
            return session.query(
                func.sum(TablePlayerRound.score)
            ).filter(and_(
                TablePlayerRound.player_key == player_id
            )).scalar()

    def get_total_decknukes_issued(self, player_id: int) -> int:
        with self.eng.session_mgr() as session:
            return session.query(func.count(TablePlayerRound.is_nuked_hand)).filter(and_(
                TablePlayerRound.player_key == player_id,
                TablePlayerRound.is_nuked_hand
            )).scalar()

    def get_total_decknukes_caught(self, player_id: int) -> int:
        with self.eng.session_mgr() as session:
            return session.query(func.count(TablePlayerRound.is_nuked_hand_caught)).filter(and_(
                TablePlayerRound.player_key == player_id,
                TablePlayerRound.is_nuked_hand_caught
            )).scalar()

    def get_all_cards(self, player_id: int) -> int:
        """Marks all the cards in the hand as 'nuked' for a player who had chosen to 'decknuke' their cards"""
        with self.eng.session_mgr() as session:
            return len(session.query(TablePlayerHand).filter(and_(
                TablePlayerHand.player_key == player_id,
            )).all())

    def get_nonreplaceable_cards(self, player_id: int) -> int:
        """Gets the cards in the deck that meet the criteria for being replaced
        (have been picked or have been nuked)"""
        with self.eng.session_mgr() as session:
            return len(session.query(TablePlayerHand).filter(and_(
                TablePlayerHand.player_key == player_id,
                not_(or_(
                    TablePlayerHand.is_picked,
                    TablePlayerHand.is_nuked
                ))
            )).all())

    def empty_hand(self, player_id: int):
        """Handles emptying the hand, generally handled at the end of a game"""
        with self.eng.session_mgr() as session:
            self.log.debug(f'Emptying player id {player_id}\'s hand...')
            # Get the hands we want to remove
            hands = session.query(TablePlayerHand).filter(TablePlayerHand.player_key == player_id).all()
            for hand in hands:
                # We must delete individually
                session.delete(hand)

    def set_nuke_cards(self, player_id: int):
        """Marks all the cards in the hand as 'nuked' for a player who had chosen to 'decknuke' their cards"""
        with self.eng.session_mgr() as session:
            self.log.debug('Flagging player\'s hand as nuked')
            session.query(TablePlayerHand).filter(and_(
                TablePlayerHand.player_key == player_id,
            )).update({
                TablePlayerHand.is_nuked: True
            })
            self.log.debug('Pulling player\'s card ids')
            player_cards = session.query(TablePlayerHand).filter(and_(
                TablePlayerHand.player_key == player_id
            )).all()
            card_ids = [x.answer_card_key for x in player_cards]
            self.log.debug(f'Incrementing count on {len(card_ids)} cards for times nuked.')
            session.query(TableAnswerCard).filter(TableAnswerCard.answer_card_id.in_(card_ids)).update({
                TableAnswerCard.times_burned: TableAnswerCard.times_burned + 1
            })

    def set_cards_in_hand(self, player_id: int, cards: List[TableAnswerCard]):
        """Takes a card into the player's hand"""
        with self.eng.session_mgr() as session:
            # Determine if space for a new card (any picked / nuked cards?)
            all_cards = session.query(TablePlayerHand).filter(and_(
                TablePlayerHand.player_key == player_id,
            )).all()
            total_card_cnt = len(all_cards)
            available_slots = session.query(TablePlayerHand).filter(and_(
                TablePlayerHand.player_key == player_id,
                or_(
                    TablePlayerHand.is_picked,
                    TablePlayerHand.is_nuked
                )
            )).all()
            self.log.debug(f'{len(available_slots)} open slots found for user out of {total_card_cnt}. '
                           f'{len(cards)} to try to add.')
            if len(available_slots) >= len(cards):
                # Replace the first slot with a card
                self.log.debug('Existing slot(s) were equal to or greater than dealt cards.')
                for i, card in enumerate(cards):
                    slot: TablePlayerHand
                    slot = available_slots[i]
                    self.log.debug(f'Replacing card at slot {slot.card_pos}.')
                    slot.is_nuked = slot.is_picked = False
                    slot.answer_card_key = card.answer_card_id
                    session.add(slot)
            elif len(available_slots) == 0 and total_card_cnt + len(cards) <= 5:
                self.log.debug('No slots available, but total cards plus cards to add were at or less than '
                               'the limit. Creating new cards.')
                taken_positions = [x.card_pos for x in all_cards]
                available_positions = [i for i in range(5) if i not in taken_positions]
                # Possibly dealing with totally new game
                for i, card in enumerate(cards):
                    self.log.debug(f'Adding card to new slot {available_positions[i]}...')
                    session.add(TablePlayerHand(
                        card_pos=available_positions[i],
                        player_key=player_id,
                        answer_card_key=card.answer_card_id
                    ))

    def mark_chosen_pick(self, player_id: int, game_round_id: int):
        """When a pick is chosen by a judge, this method handles marking those cards as chosen in the db
        for better tracking"""
        with self.eng.session_mgr() as session:
            # Get card id of this round's picks by this user, mark them as chosen
            answer_cards = session.query(TableAnswerCard).join(
                TablePlayerPick, TableAnswerCard.answer_card_id == TablePlayerPick.answer_card_key).filter(and_(
                    TablePlayerPick.player_key == player_id,
                    TablePlayerPick.game_round_key == game_round_id,
                )).all()
            for acard in answer_cards:
                # Update the card
                acard.times_chosen += 1
                session.add(acard)

    def set_picked_card(self, player_id: int, game_round_id: int, slack_user_hash: str, position: int,
                        card: PlayerHandCardType):
        """Handles the process of setting a picked card in various tables"""
        with self.eng.session_mgr() as session:
            # Move card to player_pick
            session.add(TablePlayerPick(
                player_key=player_id,
                game_round_key=game_round_id,
                slack_user_hash=slack_user_hash,
                card_order=position,
                answer_card_key=card.answer_card_key
            ))
            # Mark card in the hand as picked
            session.query(TablePlayerHand).filter(and_(
                TablePlayerHand.player_key == player_id,
                TablePlayerHand.hand_id == card.hand_id
            )).update({
                TablePlayerHand.is_picked: True
            })
            # Increment times picked
            session.query(TableAnswerCard).filter(
                TableAnswerCard.answer_card_id == card.answer_card_key
            ).update({
                TableAnswerCard.times_picked: TableAnswerCard.times_picked + 1
            })

    def get_picks_as_str(self, player_id: int, game_round_id: int) -> List[str]:
        """Grabs the player's picks and renders them in a pipe-delimited string in the order that
        they were selected"""
        with self.eng.session_mgr() as session:
            picks: List[TableAnswerCard]
            picks = session.query(TableAnswerCard).join(
                TablePlayerPick, TablePlayerPick.answer_card_key == TableAnswerCard.answer_card_id).\
                filter(and_(
                    TablePlayerPick.player_key == player_id,
                    TablePlayerPick.game_round_key == game_round_id
                )).order_by(TablePlayerPick.card_order).all()
            return [p.card_text for p in picks]

    def get_player_hand(self, player_id: int) -> PlayerHandType:
        with self.eng.session_mgr() as session:
            cards = session.query(
                TablePlayerHand.answer_card_key,
                TableAnswerCard.card_text,
                TablePlayerHand.player_key,
                TablePlayerHand.hand_id
            ).join(TablePlayerHand, TableAnswerCard.answer_card_id == TablePlayerHand.answer_card_key).filter(and_(
                    TablePlayerHand.player_key == player_id,
                )).order_by(TablePlayerHand.hand_id).all()
            session.expunge_all()
        return cards

    def handle_player_new_round(self, player_id: int, game_round_id: int, game_id: int, is_arc: bool,
                                is_arp: bool):
        with self.eng.session_mgr() as session:
            session.add(TablePlayerRound(player_key=player_id, game_key=game_id, game_round_key=game_round_id,
                                         is_arp=is_arp, is_arc=is_arc))

    def get_player_stats(self, player_id: int) -> Dict:
        with self.eng.session_mgr() as session:
            # pick/choose stats
            pick_stats_q = session.query(
                TableGameRound.game_round_id,
                TableGameRound.start_time.label('round_start'),
                TablePlayer.display_name,
                TablePlayerPick.created_date.label('pick_timestamp'),
                (TablePlayerPick.created_date - TableGameRound.start_time).label('duration_before_pick'),
                TableGameRound.end_time.label('round_end')
            ).join(TablePlayerPick, TablePlayerPick.game_round_key == TableGameRound.game_round_id).\
                join(TablePlayer, TablePlayerPick.slack_user_hash == TablePlayer.slack_user_hash).\
                filter(and_(
                    TableGameRound.end_time.isnot(None),
                    TablePlayer.player_id == player_id
                ))

            pick_stats_df = pd.read_sql(pick_stats_q.statement, session.bind)
            slowest_pick_idx = pick_stats_df['duration_before_pick'].idxmax()
            slowest_pick = pick_stats_df.loc[slowest_pick_idx, 'duration_before_pick']

            fastest_pick_idx = pick_stats_df['duration_before_pick'].idxmin()
            fastest_pick = pick_stats_df.loc[fastest_pick_idx, 'duration_before_pick']

            avg_pick_time = pick_stats_df['duration_before_pick'].mean()

            total_score = session.query(
                func.sum(TablePlayerRound.score)
            ).filter(and_(
                TablePlayerRound.player_key == player_id
            )).scalar()

            total_games_played = session.query(func.count(func.distinct(TablePlayerRound.game_key))).filter(
                TablePlayerRound.player_key == player_id
            ).scalar()

            total_rounds_played = session.query(func.count(func.distinct(TablePlayerRound.game_round_key))).filter(
                TablePlayerRound.player_key == player_id
            ).scalar()

            total_rounds_won = session.query(func.count(func.distinct(TablePlayerRound.game_round_key))).filter(
                TablePlayerRound.player_key == player_id,
                TablePlayerRound.score > 0
            ).scalar()

            total_decknukes_issued = session.query(func.count(TablePlayerRound.is_nuked_hand)).filter(and_(
                TablePlayerRound.player_key == player_id,
                TablePlayerRound.is_nuked_hand
            )).scalar()

            total_decknukes_caught = session.query(func.count(TablePlayerRound.is_nuked_hand_caught)).filter(and_(
                TablePlayerRound.player_key == player_id,
                TablePlayerRound.is_nuked_hand_caught
            )).scalar()

            if total_decknukes_issued > 0:
                noncaught_nukes = total_decknukes_issued - total_decknukes_caught
                decknuke_success = noncaught_nukes / total_decknukes_issued
            else:
                decknuke_success = '#Nevernuked'

            round_success_rate = total_rounds_won / total_rounds_played

            return {
                'Slowest Pick': slowest_pick,
                'Fastest Pick': fastest_pick,
                'Average pickling time': avg_pick_time,
                'overall score': total_score,
                'games played': total_games_played,
                'rounds endured': total_rounds_played,
                'round success rate': f'{round_success_rate:.1%} ({total_rounds_won}/{total_rounds_played})',
                'decknuke success rate': f'{decknuke_success:.1%} ({noncaught_nukes}/{total_decknukes_issued})',
                'rounds since last score': 'TBD',
                'most agreeable judge': 'TBD',
                'least agreeable judge': 'TBD'
            }
