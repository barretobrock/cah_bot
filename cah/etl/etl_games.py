
game_tables = ['games', 'gamesettings', 'gamerounds', 'playerrounds']


if __name__ == '__main__':
    from cah.etl.etl_all import ETL
    etl = ETL(tables=game_tables)
    etl.etl_games()
