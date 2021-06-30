
deck_tables = ['decks', 'question_cards', 'answer_cards']


if __name__ == '__main__':
    from cah.etl.etl_all import ETL
    etl = ETL(tables=deck_tables)
    etl.etl_decks()
