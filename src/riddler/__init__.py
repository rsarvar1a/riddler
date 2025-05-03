from discord import AllowedMentions, Interaction, Intents
from discord.ext.commands import DefaultHelpCommand
from discord.ext.commands.bot import Bot
from dotmap import DotMap
from riddler import admin, embeds, logging, marathon
from riddler.config import Config

class Riddler(Bot):
    COGS = (admin, marathon)

    def __init__(self, *, config: Config):
        self.config = DotMap(config.__dict__)

        self.logger, _, _ = logging.make_logger(name='Riddler', severity=logging.severity(config.log_level))
        self.logger.debug('debug mode enabled')

        super().__init__(
            self.config.prefix,
            allowed_mentions=AllowedMentions(everyone=False),
            case_insensitive=True,
            help_command=DefaultHelpCommand(dm_help=True),
            intents=Intents.all()
        )

        self.owner_ids = config.owners

    def run(self, token: str, *, reconnect: bool = True) -> None:
        """
        Runs the discord bot, blocking.
        """
        return super().run(token, reconnect=reconnect, log_level=self.logger.getEffectiveLevel() + 10)        

    async def send_ethereal(self, interaction: Interaction, *, followup = False, ethereal = True, ephemeral = True, **kwargs):
        """
        Sends an ethereal message, which is an autodeleting ephemeral.
        """
        embed = embeds.make_embed(self, **kwargs)
        if followup:
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(embed=embed, delete_after=5 if ethereal else None, ephemeral=ephemeral)

    async def setup_hook(self) -> None:
        """
        Loads all modules (cogs) into the bot.
        """
        extensions = [m.__name__.split('.')[1].capitalize() for m in Riddler.COGS]
        self.logger.info(f'loading extensions: {', '.join(extensions)}')
        for module in Riddler.COGS:
            await module.setup(self)
