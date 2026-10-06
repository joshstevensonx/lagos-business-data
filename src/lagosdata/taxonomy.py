# 18-category taxonomy for Anthony Community Media database
CATS = ["Restaurants","Hotels","Gyms","Salons","Barbers","Medical Centres","Dentists",
        "Pharmacies","Schools","Churches","Supermarkets","Boutiques","Home Services",
        "Real Estate","Professional Services","Auto Services","Event Businesses","Caterers"]

# ordered keyword rules: (primary_category, [keywords matched against lowercased source label])
RULES = [
 ("Barbers",      ["barb"]),
 ("Pharmacies",   ["pharmac","chemist","drug store","patent medicine"]),
 ("Dentists",     ["dent","orthodont"]),
 ("Medical Centres",["hospital","clinic","medical","health","diagnost","laborator","optic","optometr",
                     "physiotherap","maternity","nursing home","doctor","eye centre","eye center","wellness"]),
 ("Salons",       ["salon","spa","hair","nail","beauty","makeup","make-up","cosmetic","braid","massage"]),
 ("Gyms",         ["gym","fitness","sport","recreation","swim","football","athletic","yoga","pilates","martial art"]),
 ("Hotels",       ["hotel","guest house","guesthouse","lodge","suites","motel","apartment hotel","hostel"]),
 ("Caterers",     ["cater"]),
 ("Event Businesses",["event","party","photograph","videograph","rental","hall","wedding","decor","photo lab","studio",
                      "entertainment","lounge","bar","club","dj","mc "]),
 ("Restaurants",  ["restaurant","fast food","food","eatery","buka","bukka","cafe","café","canteen",
                   "bakery","confection","grill","suya","pizza","chop","kitchen","juice","ice cream","jamaican","chinese","african","thai","italian","fine dining","bistro","diner","shawarma","bar","lounge","pub"]),
 ("Supermarkets", ["supermarket","grocer","provision","mart","market","store  ","mini mart","shopping centre",
                   "shopping center","shoprite","superstore"]),
 ("Churches",     ["church","parish","chapel","ministr","cathedral","assembl","mosque","fellowship","gospel","place of worship","association / organization","worship"]),
 ("Schools",      ["school","college","academy","nursery","creche","crèche","educat","tutor","lesson",
                   "montessori","university","polytechnic","institute","training centre","training center",
                   "bookshop","book shop","library","stationer"]),
 ("Real Estate",  ["real estate","estate agent","property","propert","realtor","housing development","apartment building","short term apartment","land ","surveyor","valuer",
                   "facility management","letting"]),
 ("Auto Services",["auto","car wash","carwash","mechanic","vulcaniz","vulcanis","tyre","tire","panel beat",
                   "spare part","motor","vehicle","towing","filling station","petrol","fuel","transport","parking garage","car inspection","parking lot",
                   "logistic","courier","haulage","dispatch","driving school"]),
 ("Home Services",["plumb","electric","carpenter","clean","laundry","dry clean","fumigat","pest",
                   "interior","furnitur","home","bedding","upholster","paint","aluminium","aluminum",
                   "welder","welding","borehole","solar","inverter","generator","ac repair","air condition",
                   "tailor","cobbler","hardware","building","construct","tiler","pop ","curtain","gardening",
                   "security","satellite","dstv"]),
 ("Boutiques",    ["boutique","cloth","fashion","apparel","wear","perfume","beauty supply","shoe","footwear","fabric","textile","bag",
                   "jewel","watch","accessor","thrift","okrika","retail","shop","electronic","phone","telecom",
                   "computer","gadget","gift","cosmetics shop","plaza"]),
 ("Professional Services",["professional","legal","law","attorney","barrister","solicitor","account","audit",
                   "tax","consult","bank","financ","insur","business center","business centre","microfinance","bureau de change","investment",
                   "print","design","advertis","market","media","branding","it service","software","tech",
                   "web","data","recruit","hr ","logistics service","travel","tour","immigration","notary",
                   "business service","secretarial","cyber","internet","courier service","register"]),
]

def normalise(label: str, name: str = "") -> str:
    """Map a raw category label (falling back to business name) onto one of the 18."""
    blob = ((label or "") + " " + (name or "")).lower()
    if "barb" in blob:
        return "Barbers"
    if "dent" in blob or "orthodont" in blob:
        return "Dentists"
    for src in (label or "", name or ""):
        s = " " + src.lower().replace("/", " ").replace("-", " ") + " "
        for cat, keys in RULES:
            for k in keys:
                if k.strip() and k.strip() in s:
                    return cat
    return ""
