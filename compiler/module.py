import json
import re
from typing import List, Union

import aiohttp
import discord
from discord.ext import commands
from pie import check, i18n, utils

_ = i18n.Translator("modules/compsci").translate


class Compiler(commands.Cog):
    """Compiling code so you don't have to."""

    def __init__(self, bot):
        self.bot = bot
        self.compilers = []
        self.languages = []

    async def _cog_update(self, ctx):
        async with ctx.typing():
            async with aiohttp.ClientSession() as session:
                async with session.get("https://wandbox.org/api/list.json") as response:
                    compilers = await response.json()
                    response.raise_for_status()
                    self.compilers = compilers
            languages = []
            for item in self.compilers:
                lang = next(
                    (x for x in languages if x["name"] == item["language"]), None
                )
                if lang is None:
                    languages.append(
                        {
                            "name": item["language"],
                            "compilers": [item["name"]],
                            "templates": item["templates"],
                        }
                    )
                else:
                    if item["name"] in lang["compilers"]:
                        await self.log(
                            level="info",
                            message=f"Compiler - Load collision: {item['name']}",
                        )
                    else:
                        lang["compilers"].append(item["name"])
                        lang["templates"].extend(item["templates"])
                        lang["templates"] = list(set(lang["templates"]))
            self.languages = sorted(languages, key=lambda d: d["name"])

    def _create_language_embeds(self, ctx) -> List[discord.Embed]:
        embeds = []
        for idx, lang in enumerate(self.languages):
            if idx % 24 == 0:
                try:
                    embeds.append(embed)
                except Exception:
                    pass
                embed = utils.discord.create_embed(
                    author=ctx.author,
                    title=_(ctx, "Compiler languages"),
                )
            value = (
                f"{len(lang['compilers'])} compilers"
                if len(lang["compilers"]) > 1
                else f"{len(lang['compilers'])} compiler"
            )
            embed.add_field(name=lang["name"], value=value)
        embeds.append(embed)
        return embeds

    def _create_language_info_embeds(self, ctx, language) -> List[discord.Embed]:
        embeds = []
        compilers = [
            elem
            for elem in self.compilers
            if elem["language"].lower() == language.lower()
        ]
        lang = next(
            item for item in self.languages if item["name"].lower() == language.lower()
        )
        for idx, comp in enumerate(compilers):
            if idx % 24 == 0:
                try:
                    embeds.append(embed)
                except Exception:
                    pass
                embed = utils.discord.create_embed(
                    author=ctx.author,
                    title=_(ctx, f"{language.title()} compilers"),
                    description=f"Templates available: `{lang['templates']}`",
                )
            name = comp["name"] if idx > 0 else f"{comp['name']} (default)"
            value = f"Version: {comp['version']}"
            embed.add_field(name=name, value=value)
        embeds.append(embed)
        return embeds

    async def _run_compiler(self, compiler, code, highlighter) -> Union[dict, None]:
        params = {
            "compiler": compiler["name"],
            "code": code,
            "options": "",
            "stdin": "",
            "compiler-option-raw": "",
            "runtime-option-raw": "",
            "save": True,
        }  # TODO add additional functionality

        try:
            async with aiohttp.ClientSession(raise_for_status=True) as session:
                async with session.post(
                    "https://wandbox.org/api/compile.json", data=json.dumps(params)
                ) as response:
                    dic = await response.json()
            if "signal" in dic:
                dic["status"] = dic["signal"]
                return dic
            elif dic["status"] != "0":
                params["code"] = f"{highlighter}\n{code}"
                async with aiohttp.ClientSession(raise_for_status=True) as session:
                    async with session.post(
                        "https://wandbox.org/api/compile.json", data=json.dumps(params)
                    ) as response:
                        dic = await response.json()
        except aiohttp.ClientResponseError as e:
            embed = self.create_embed(
                author=ctx.message.author,
                title="Critical error:",
                color=config.color_error,
            )
            embed.add_field(
                name="API replied with:",
                value=f"`{e.status} {e.message}`"
                "\n*This could mean WandBox is experiencing an outage, a network connection error has occured, or you provided a wrong request.*",
                inline=False,
            )

            await ctx.send(embed=embed)
            return
        return dic

    @check.acl2(check.ACLevel.MEMBER)
    @commands.group(name="compiler")
    async def compiler(self, ctx):
        """Compiler information"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command.qualified_name)

    @check.acl2(check.ACLevel.MEMBER)
    @compiler.group(name="language")
    async def compiler_language(self, ctx):
        """Compiler information"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command.qualified_name)

    @check.acl2(check.ACLevel.MEMBER)
    @compiler_language.command(name="list")
    async def compiler_language_list(self, ctx):
        """List languages available to use with the compiler."""
        await self._cog_update(ctx)

        embeds = self._create_language_embeds(ctx)
        scrollable_embed = utils.ScrollableEmbed(ctx, embeds)

        await scrollable_embed.scroll()

    @check.acl2(check.ACLevel.MEMBER)
    @compiler_language.command(name="info")
    async def compiler_language_info(self, ctx, language: str):
        """List compilers available to use with the selected language.

        Args:
            language (str): Language to view
        """
        await self._cog_update(ctx)

        embeds = self._create_language_info_embeds(ctx, language)
        scrollable_embed = utils.ScrollableEmbed(ctx, embeds)

        await scrollable_embed.scroll()

    @check.acl2(check.ACLevel.MEMBER)
    @compiler.command(name="template")
    async def compiler_template(self, ctx, template: str):
        """Get a template to start with.

        Args:
            template (str): Obtainable in the `compiler language info` command.
        """
        if self.compilers == [] or self.languages == []:
            await self._cog_update(ctx)

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://wandbox.org/api/template/{template}"
            ) as response:
                response.raise_for_status()
                dic = await response.json()

        code = f"```{dic['code']}```"

        await ctx.reply(code)

    @check.acl2(check.ACLevel.MEMBER)
    @commands.command(name="compile")
    async def compiler_compile(self, ctx, comp_or_lang: str):
        """Get a template to start with.

        Args:
            comp_or_lang (str): Either a language (that uses the default compiler) or an exact compiler to use.
        """
        if self.compilers == [] or self.languages == []:
            await self._cog_update(ctx)

        comp = next(
            (x for x in self.compilers if comp_or_lang.lower() == x["name"].lower()),
            None,
        )
        lang = next(
            (x for x in self.languages if comp_or_lang.lower() in x["name"].lower()),
            None,
        )
        if not comp and not lang:
            comp = next(
                (
                    x
                    for x in self.compilers
                    if comp_or_lang.lower() == x["display-name"].lower()
                ),
                None,
            )
            if not comp:
                await ctx.reply("No language or compiler found.")
                return
        elif not comp and lang:
            comp = next(
                (
                    x
                    for x in self.compilers
                    if lang["compilers"][0].lower() == x["name"].lower()
                ),
                None,
            )
        message = ctx.message
        try:
            reg_result = re.search(r"\`\`\`([^\n]+)?([^\`]*)\`\`\`", message.content)
            code = reg_result.group(2)
            highlighter = reg_result.group(1)
        except AttributeError:
            embed = utils.discord.create_embed(
                author=ctx.message.author,
                title="Critical error:",
                description="You must attach a code-block containing code to your message",
            )
            await ctx.reply(embed=embed)
            return

        confirm_embed = utils.discord.create_embed(
            author=ctx.message.author,
            title=f"Do you want to run {comp['display-name']} compiler with the following code?",
            description=f"```{highlighter}\n{code}```",
        )
        confirm_view = utils.ConfirmView(ctx, confirm_embed)
        result = await confirm_view.send()

        if not result:
            return

        async with ctx.typing():
            result = await self._run_compiler(comp, code, highlighter)

        if result is None:
            return

        print(result)

        result_embed = utils.discord.create_embed(
            author=ctx.message.author,
            title="Compilation results",
            description=f"Status: {result['status']}",
            url=result["url"],
        )
        stdout = discord.utils.escape_mentions(result["program_output"])
        stderr = discord.utils.escape_mentions(result["program_error"])

        if len(stdout) > 0:
            if len(stdout) > 1018:
                stdout = stdout[:1018]
                result_embed.description = "Output was too long. Click the `Compilation results` hyperlink to see the full output."
            result_embed.add_field(name="Program Output", value=f"```{stdout}```")
        if len(stderr) > 0:
            if len(stderr) > 1018:
                stderr = stderr[:1018]
                result_embed.description = "Output was too long. Click the `Compilation results` hyperlink to see the full output."
            result_embed.add_field(name="Program Error", value=f"```{stderr}```")

        await ctx.reply(embed=result_embed)


async def setup(bot) -> None:
    await bot.add_cog(Compiler(bot))
