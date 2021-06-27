from cah.etl.etl_all import ETL


if __name__ == '__main__':
    etl = ETL(tables=['players'])
    etl.etl_players()
