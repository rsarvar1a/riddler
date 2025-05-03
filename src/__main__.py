
import argparse
import dotenv
import os
import riddler

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', help='path to a config.toml file', default='config.toml')
    parser.add_argument('--dotenv', help='path to a .env file', default='.env')
    args = parser.parse_args()

    dotenv.load_dotenv(args.dotenv, override=True)
    config = riddler.Config.load(args.config)
    bot = riddler.Riddler(config=config)
    bot.run(os.getenv('DISCORD_TOKEN'))

if __name__ == '__main__':
    main()
