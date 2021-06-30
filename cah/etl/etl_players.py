
player_tables = ['players']


if __name__ == '__main__':
    from cah.etl.etl_all import ETL
    etl = ETL(tables=player_tables)
    etl.etl_players()
