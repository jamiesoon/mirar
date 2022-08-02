CREATE TABLE IF NOT EXISTS candidates (
    candid BIGINT PRIMARY KEY,
    name VARCHAR(15),
    ra REAL,
    dec REAL,
    fwhm REAL,
    jd REAL,
    fid INT,
    diffimname VARCHAR(255),
    sciimname VARCHAR(255),
    refimname VARCHAR(255),
    magpsf REAL,
    sigmapsf REAL,
    chipsf REAL,
    aimage REAL,
    bimage REAL,
    aimagerat REAL,
    bimagerat REAL,
    elong REAL,
    psra1 REAL,
    psdec1 REAL,
    scorr REAL,
    xpos REAL,
    ypos REAL,
    magzpsci REAL,
    magzpsciunc REAL,
    tmjmag1 REAL,
    tmhmag1 REAL,
    tmkmag1 REAL,
    tmobjectid1 VARCHAR(25)
);