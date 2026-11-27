"""Demo catalog: public-domain books (spec note 4). Books with a ``text``
file come from Project Gutenberg (via the NLTK Gutenberg corpus) and can be
read in the Reading Companion; the others are catalog entries only."""

# (key, title, author, category, year, price, keywords, description, text file, cover colour, motif)
BOOKS = [
    ("emma", "Emma", "Jane Austen", "Literature", 1815, 9.99, ["romance", "society", "matchmaking"],
     "A clever young woman in a quiet English village keeps arranging other people's love lives - and keeps getting them wrong.",
     "austen-emma.txt", "#6B2737", "envelope"),
    ("persuasion", "Persuasion", "Jane Austen", "Literature", 1817, 8.49, ["romance", "second chances", "navy"],
     "Eight years after she was persuaded to break off an engagement, Anne Elliot meets the naval captain she refused.",
     "austen-persuasion.txt", "#2C4A5A", "waves"),
    ("sense", "Sense and Sensibility", "Jane Austen", "Literature", 1811, 8.99, ["romance", "sisters", "family"],
     "Two sisters - one sensible, one passionate - face love, money and disappointment after their father's death.",
     "austen-sense.txt", "#5A6B35", "tree"),
    ("blake", "Songs of Innocence and of Experience", "William Blake", "Poetry", 1789, 5.99, ["poems", "childhood", "nature"],
     "Short illustrated poems that look at the world first through the eyes of innocence and then through experience.",
     "blake-poems.txt", "#E9E2D0", "sun"),
    ("bryant", "Stories to Tell to Children", "Sara Cone Bryant", "Children", 1918, 6.49, ["fairy tales", "stories", "bedtime"],
     "A collection of short fables and folk tales chosen to be read aloud to young children.",
     "bryant-stories.txt", "#E8B04A", "moon"),
    ("busterbear", "The Adventures of Buster Bear", "Thornton W. Burgess", "Children", 1920, 4.99, ["animals", "forest", "bear"],
     "Buster Bear arrives in the Green Forest and the other animals must learn what kind of neighbour he will be.",
     "burgess-busterbrown.txt", "#2F4A3A", "tree"),
    ("alice", "Alice's Adventures in Wonderland", "Lewis Carroll", "Children", 1865, 7.99, ["fantasy", "dream", "nonsense"],
     "Alice follows a white rabbit down a hole into a world of riddles, tea parties and a very angry queen.",
     "carroll-alice.txt", "#4A2C4A", "keyhole"),
    ("ball", "The Ball and the Cross", "G. K. Chesterton", "Philosophy", 1909, 10.99, ["faith", "duel", "debate"],
     "An atheist and a believer agree to fight a duel over their beliefs, but all of London keeps stopping them.",
     "chesterton-ball.txt", "#3A4750", "cross"),
    ("fatherbrown", "The Wisdom of Father Brown", "G. K. Chesterton", "Mystery", 1914, 9.49, ["detective", "crime", "priest"],
     "Twelve mysteries solved by a small, mild Catholic priest who understands criminals better than the police do.",
     "chesterton-brown.txt", "#1E2A44", "magnifier"),
    ("thursday", "The Man Who Was Thursday", "G. K. Chesterton", "Mystery", 1908, 9.99, ["anarchists", "spy", "nightmare"],
     "A poet-detective infiltrates a council of seven anarchists, each named after a day of the week.",
     "chesterton-thursday.txt", "#B5452F", "moon"),
    ("parents", "The Parent's Assistant", "Maria Edgeworth", "Children", 1796, 6.99, ["moral tales", "family", "lessons"],
     "Moral stories for children about honesty, kindness and good sense, written by one of the first children's authors.",
     "edgeworth-parents.txt", "#8A9A7B", "heart"),
    ("mobydick", "Moby Dick", "Herman Melville", "Adventure", 1851, 12.99, ["sea", "whale", "obsession"],
     "Ishmael sails on the whaler Pequod, whose captain Ahab will stop at nothing to kill the white whale.",
     "melville-moby_dick.txt", "#2C4A5A", "whale"),
    ("paradise", "Paradise Lost", "John Milton", "Poetry", 1667, 11.49, ["epic", "fall", "heaven"],
     "The epic poem of Satan's rebellion and the fall of Adam and Eve, told in grand blank verse.",
     "milton-paradise.txt", "#1E2A44", "sun"),
    ("caesar", "Julius Caesar", "William Shakespeare", "Drama", 1599, 5.49, ["rome", "politics", "betrayal"],
     "Brutus joins the plot to kill Caesar to save the Republic, and Rome falls into civil war.",
     "shakespeare-caesar.txt", "#6B2737", "dagger"),
    ("hamlet", "Hamlet", "William Shakespeare", "Drama", 1603, 5.99, ["revenge", "prince", "ghost"],
     "The Prince of Denmark is asked by his father's ghost to take revenge on the uncle who now wears the crown.",
     "shakespeare-hamlet.txt", "#3A4750", "crown"),
    ("macbeth", "Macbeth", "William Shakespeare", "Drama", 1606, 5.49, ["ambition", "witches", "murder"],
     "A brave Scottish general hears a prophecy that he will be king - and decides to make it come true.",
     "shakespeare-macbeth.txt", "#4A1F1F", "crown"),
    ("leaves", "Leaves of Grass", "Walt Whitman", "Poetry", 1855, 7.49, ["america", "nature", "self"],
     "Whitman's celebration of himself, democracy, the body and the American landscape in free verse.",
     "whitman-leaves.txt", "#5A6B35", "grass"),
    # ---- catalog-only titles (no Reading Companion text) ----
    ("pride", "Pride and Prejudice", "Jane Austen", "Literature", 1813, 9.49, ["romance", "society", "family"],
     "Elizabeth Bennet and the proud Mr Darcy misjudge each other in Austen's best-loved novel.",
     None, "#B5452F", "heart"),
    ("frankenstein", "Frankenstein", "Mary Shelley", "Science Fiction", 1818, 8.99, ["monster", "science", "creation"],
     "A young scientist builds a living creature and then abandons it, with terrible results.",
     None, "#2F4A3A", "bolt"),
    ("dracula", "Dracula", "Bram Stoker", "Horror", 1897, 9.99, ["vampire", "gothic", "letters"],
     "Told in letters and diaries, a group of friends hunts the ancient vampire who has come to England.",
     None, "#4A1F1F", "moon"),
    ("timemachine", "The Time Machine", "H. G. Wells", "Science Fiction", 1895, 6.99, ["time travel", "future", "class"],
     "An inventor travels to the year 802,701 and finds humanity split into two very different races.",
     None, "#1E2A44", "clock"),
    ("worlds", "The War of the Worlds", "H. G. Wells", "Science Fiction", 1898, 7.49, ["aliens", "invasion", "mars"],
     "Martians land in the English countryside and nothing humanity has can stop them.",
     None, "#6B2737", "planet"),
    ("treasure", "Treasure Island", "Robert Louis Stevenson", "Adventure", 1883, 7.99, ["pirates", "treasure", "sea"],
     "Young Jim Hawkins finds a treasure map and sails with the one-legged cook Long John Silver.",
     None, "#E8B04A", "ship"),
    ("littlewomen", "Little Women", "Louisa May Alcott", "Literature", 1868, 8.99, ["sisters", "growing up", "family"],
     "The four March sisters grow up during the American Civil War.",
     None, "#8A9A7B", "heart"),
    ("janeeyre", "Jane Eyre", "Charlotte Bronte", "Literature", 1847, 9.49, ["governess", "gothic", "independence"],
     "An orphan becomes a governess at Thornfield Hall and falls in love with its secretive owner.",
     None, "#3A4750", "candle"),
    ("wuthering", "Wuthering Heights", "Emily Bronte", "Literature", 1847, 8.99, ["moors", "passion", "revenge"],
     "The wild love between Catherine and Heathcliff destroys two families on the Yorkshire moors.",
     None, "#2C4A5A", "grass"),
    ("origin", "On the Origin of Species", "Charles Darwin", "Science", 1859, 13.99, ["evolution", "biology", "natural selection"],
     "Darwin's argument that species change over time through natural selection.",
     None, "#5A6B35", "leaf"),
    ("relativity", "Relativity: The Special and General Theory", "Albert Einstein", "Science", 1916, 11.99,
     ["physics", "space", "time"],
     "Einstein's own explanation of relativity for readers without advanced mathematics.",
     None, "#E9E2D0", "atom"),
    ("beagle", "The Voyage of the Beagle", "Charles Darwin", "Science", 1839, 10.49, ["travel", "nature", "islands"],
     "Darwin's journal of his five-year voyage around the world, including the Galapagos Islands.",
     None, "#2C4A5A", "ship"),
    ("sherlock", "The Adventures of Sherlock Holmes", "Arthur Conan Doyle", "Mystery", 1892, 8.49,
     ["detective", "crime", "london"],
     "Twelve cases of the great detective Sherlock Holmes and his friend Dr Watson.",
     None, "#1E2A44", "magnifier"),
    ("christmascarol", "A Christmas Carol", "Charles Dickens", "Literature", 1843, 4.99, ["ghosts", "christmas", "redemption"],
     "The miser Ebenezer Scrooge is visited by three ghosts on Christmas Eve.",
     None, "#6B2737", "candle"),
    ("artofwar", "The Art of War", "Sun Tzu", "Philosophy", -500, 5.99, ["strategy", "war", "leadership"],
     "The ancient Chinese guide to strategy, still read by generals and business leaders.",
     None, "#B5452F", "mountain"),
]

TABOO_WORDS = ["idiot", "stupid", "dumb", "trash", "garbage", "moron", "junk"]

# username, full name, email, role, status, balance, warnings
USERS = [
    ("admin", "Store Admin", "admin@bookorbit.local", "SU", "ACTIVE", 0.0, 0),
    ("yixin", "Yixin Chen", "yixin@bookorbit.local", "SU", "ACTIVE", 0.0, 0),
    ("alice", "Alice Morgan", "alice@example.com", "RC", "ACTIVE", 30.02, 0),
    ("selina", "Selina Zhu", "selina@example.com", "VC", "ACTIVE", 85.00, 0),
    ("evan", "Evan Florentino", "evan@example.com", "RC", "ACTIVE", 12.00, 2),
    ("zakiah", "Zakiah Almontaser", "zakiah@example.com", "RC", "SUSPENDED", -1.00, 0),
    ("ibrahim", "Ibrahim Rahat", "ibrahim@example.com", "RC", "ACTIVE", 250.00, 0),
]

POLICIES = """# BookOrbit AI - store information (used by the chatbot's RAG)

## About BookOrbit AI
BookOrbit AI is an AI-enabled multimodal smart bookstore built by Borbit LLC for the CSC 322 Software Engineering course at The City College of New York. It sells digital editions of public-domain books, most of them from Project Gutenberg, and runs entirely on the customer's own computer.

## Team
The BookOrbit AI team members are Zakiah Almontaser, Yixin Chen, Evan Florentino, Ibrahim Rahat and Selina Zhu. The team chose the Smart Reading Companion as its creative feature.

## Store hours and contact
The online store is open 24 hours a day, 7 days a week. Customer support answers questions Monday to Friday, 9 am to 6 pm Eastern Time, at support@bookorbit.local. Suspended customers should contact a Super-User to reopen their account.

## Account types
There are four kinds of users. Visitors can browse, search, read reviews, write reviews and ask the chatbot store questions. Registered Customers sign in with their face, keep a store balance, buy books, write reviews and use the Reading Companion. VIP Customers get everything Registered Customers get plus a 10 percent discount on every purchase. Super-Users manage books, taboo words, accounts and reports.

## Registration and face sign-in
To register, enter your full name, a username and an email address, and take a face photo with your camera. BookOrbit AI keeps only a face template (numbers that describe your face), never the photo itself. To sign in, enter your username and look at the camera. After 3 failed attempts in a row the username is locked for 5 minutes.

## Store balance, deposits and fines
Customers pay from their store balance. Add funds on the My Balance page; one deposit can be up to $10,000. If you try to buy books that cost more than your balance, the purchase is rejected and a $1.00 fine is charged. An account whose balance falls below $0 is suspended: you can still sign in to the wallet to add money, and a Super-User can reopen the account once the balance is $0 or more.

## VIP program
A Registered Customer who makes more than 3 purchases or spends more than $200 is promoted to VIP Customer automatically. VIP Customers get 10 percent off every purchase. The discount starts with the purchase after the promotion. A VIP Customer whose comment is blocked loses VIP status and returns to Registered Customer.

## Reviews and ratings
Any user can rate a book from 1 to 5 stars and write a comment of up to 1000 characters. Reviews by customers who bought the book are verified and count double in the weighted average. Books with more than 3 ratings and a weighted average below 2 go on the No-Order list; books with more than 3 ratings and an average above 4 go on the To-Order list.

## Taboo words and warnings
Words on the store's taboo list are replaced by asterisks. A comment with more than 3 taboo words is blocked entirely and its author receives a warning. A Registered Customer with more than 2 warnings is suspended, and a VIP Customer with a blocked comment is demoted to Registered Customer.

## Refunds
Books are digital and unlocked immediately, so purchases are final and cannot be refunded. Fines are not refunded either.

## Smart Reading Companion
The Reading Companion opens a book chapter by chapter. It can summarize a chapter, explain a selected passage, define a word, quiz you with three questions, or answer a question using only the book's own text. Everyone signed in can read the first chapter for free; buy the book to unlock the rest.

## AI chatbot
The chatbot first looks for the answer in the store's local files (retrieval-augmented generation, RAG) and says so. If the question is not about the store, it asks the local Ollama language model and says so. Visitors can ask only about the store; customers can also ask about their own account and general questions; VIP Customers can also search inside the books; Super-Users can ask for the finance report.

## Privacy
All data stays on this computer in local text files. Nothing is sent to the internet; the language model runs locally with Ollama.
"""
