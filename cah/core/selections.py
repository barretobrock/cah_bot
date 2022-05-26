import re
from typing import (
    List,
    Optional
)
import numpy as np
from cah.logg import get_base_logger


LOG = get_base_logger().bind(child_name='selections')


class Selection:
    is_random = False       # type: bool
    random_subset = None    # type: List[int]
    player_hash = None      # type: str
    positions = None  # type: List[int]

    def parse(self, message: str, make_random_selections_now: bool = True):
        """Handles parsing a pick/choice message
        Examples:
            picks:
                > pick 2
                > pick 2 3 4                        # Multi select
                > randpick 234                      # subset
                > randpick <@other_user_hash> 234   # Randpick of other user with a subset

        """
        msg_split = message.split()
        for i, item in enumerate(msg_split):
            if i == 0:
                # Check if this is a rand(pick|choose)
                self.is_random = 'rand' in message
            elif '<@' in item:
                # User tag in message. Extract and assign to player_hash
                self.player_hash = self.extract_user_hash(message_fragment=item)
            elif re.sub(r'\W+', '', item).isnumeric():
                val_list = self.extract_ints(item)
                if self.is_random:
                    # Subsets were supplied with the randpick
                    if self.random_subset is None:
                        # Assign to new list
                        self.random_subset = val_list
                    else:
                        # Append to existing list
                        self.random_subset += val_list
                else:
                    # Direct picks
                    if self.positions is None:
                        self.positions = val_list
                    else:
                        self.positions += val_list
            if self.is_random and make_random_selections_now:
                # Handle the random selection
                self.handle_random_selection()

    @staticmethod
    def extract_ints(message_fragment: str) -> List[int]:
        """Extracts integers from a message fragment
        Examples:
            > "2,34" -> [2, 3, 4]
            > "234" -> [2, 3, 4]
        """
        # Pull out integers individually
        int_list = list(map(int, list(re.sub(r'\W+', '', message_fragment))))
        # Since these are indexes for items in a list, subtract 1 to give their true position
        #   these were initially starting from 1, so they'll need to start from 0
        return [x - 1 for x in int_list]

    @staticmethod
    def extract_user_hash(message_fragment: str) -> Optional[str]:
        # Extract the hash
        return re.search(r'(?!=<@)\w+(?=>)', message_fragment).group().upper()

    def handle_random_selection(self):
        """This is a placeholder for child methods that will replace this"""
        pass


class Pick(Selection):
    picks = None  # type: List[int]

    def __init__(self, player_hash: str, message: str, n_required: int, total_cards: int):
        """
        Args:
            player_hash: the slack user hash of the player
            message: the pick message
            n_required: the required number of answers for the question

        """
        LOG.debug(f'Received pick message: {message}')
        self.n_required = n_required
        self.total_cards = total_cards
        self.player_hash = player_hash.upper()
        # Parse the details from the message, don't make possible random selections yet though.
        self.parse(message=message, make_random_selections_now=False)

    def handle_pick(self, total_cards: int):
        # Due to the nature of picking for other absent players, sometimes we might need to change
        #   the number of total cards between when we receive the pick command and determining who the
        #   target player is. This is to mitigate against the risk that one player potentially has
        #   fewer cards than another.
        self.total_cards = total_cards
        self.handle_random_selection()
        if max(self.positions) > total_cards - 1 or min(self.positions) < 0:
            raise ValueError(f'Pick was outside the accepted range: '
                             f'0 <= {min(self.positions)} || {max(self.positions)} > {self.total_cards - 1}')
        self.picks = self.positions

    def handle_random_selection(self):
        if self.is_random:
            if self.random_subset is not None:
                if len(self.random_subset) >= self.n_required:
                    # Pick from subset
                    LOG.debug(f'Randomly selecting {self.n_required} pick(s) from subset ({self.random_subset})')
                    self.positions = np.random.choice(self.random_subset, self.n_required, replace=False).tolist()
                else:
                    raise ValueError(f'The required number of responses: {self.n_required} is greater than '
                                     f'the subset made: {self.random_subset}')
            else:
                # Picking from all available options
                LOG.debug(f'Randomly selecting {self.n_required} pick(s) from all cards')
                self.positions = np.random.choice(self.total_cards, self.n_required, replace=False).tolist()

    def __repr__(self) -> str:
        return f'<Pick(p_hash={self.player_hash}, positions={self.positions}, is_random={self.is_random},' \
               f' subset={self.random_subset})>'


class Choice(Selection):
    choice = None  # type: int

    def __init__(self, player_hash: str, message: str, all_submission_cnt: int):
        """

        Args:
            player_hash:
            message:
            all_submission_cnt: all submissions from non-judge players for the round
        """
        LOG.debug(f'Received choose message: {message}')
        self.all_submission_cnt = all_submission_cnt
        self.player_hash = player_hash.upper()
        self.parse(message=message, make_random_selections_now=True)
        if max(self.positions) > self.all_submission_cnt - 1 or min(self.positions) < 0:
            LOG.warning(f'Pick was outside the accepted range: 0 <= {min(self.positions)} || '
                        f'{max(self.positions)} > {self.all_submission_cnt - 1}')
        self.choice = self.positions[0]

    def handle_random_selection(self):
        if self.is_random:
            if self.random_subset is not None:
                if len(self.random_subset) >= 1:
                    LOG.debug(f'Randomly selecting choice from subset ({self.random_subset})')
                    self.positions = np.random.choice(self.random_subset, 1, replace=False).tolist()
                else:
                    raise ValueError('The parsed subset list was empty. Selection avoided.')
            else:
                # Picking from all available options
                LOG.debug(f'Randomly selecting choice from all submissions ({self.all_submission_cnt})')
                self.positions = np.random.choice(self.all_submission_cnt, 1, replace=False).tolist()

    def __repr__(self) -> str:
        return f'<Choice(p_hash={self.player_hash}, choice={self.choice}, is_random={self.is_random},' \
               f' subset={self.random_subset})>'
