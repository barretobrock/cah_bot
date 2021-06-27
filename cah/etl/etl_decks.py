from cah.etl.etl_all import ETL


if __name__ == '__main__':
    etl = ETL(tables=['decks', 'question_cards', 'answer_cards'])
    etl.etl_decks()
