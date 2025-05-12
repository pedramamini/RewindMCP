We're creating a Python3 project that's going to first and foremost give us pythonic access over a sqlite table that contains real time captured data from both speech to text 
through my speaker/microphone but also OCR from my screen. the database is from rewind.ai it is located in:

/Users/pedram/Library/Application Support/com.memoryvault.MemoryVault/db-enc.sqlite3

the password for this database is:

soiZ58XZJhdka55hLUp18yOtTUTDXz7Diu7Z4JzuwhRwGG13N6Z9RTVU1fGiKkuF

take a look at sqlite-peek, it's a python script able to open and peruse the DB. check out peek.txt for introspection of the DB.

here's what you're going to do, and as you knock it out, check it off:

- [ ] analyze and fully understand how text from audio and screen is stored in the database.
- [ ] create a pythonic library for interfacing directly with the sqlite database, hard code the password, that's fine. it's static
- [ ] create a CLI tool that uses the library above to pull audio transcripts:
    - [ ] relative time (last hour, last 5 hours, etc...)
    - [ ] specific time box (1pm to 5pm)
- [ ] create a CLI tool that uses the library above to search for keywords across both audio transcripts and screen OCR
    - [ ] audio hits should show the timestamp and some text content before/after the hit
    - [ ] visual hits should show the timestamp and the application
- [ ] create an MCP server that will leverage the library to expose the services provided by the CLI to GenAI models

