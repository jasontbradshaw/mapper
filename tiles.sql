pragma foreign_keys=off;

begin transaction;

create table Tile (
    x integer not null,
    y integer not null,
    zoom integer not null,
    kind text not null,
    image blob,

    -- stores the last time the tile was updated
    update_date integer not null,

    -- we want our tiles to be unique for their unique data
    unique (x, y, zoom, kind) on conflict replace
);

-- make lookups for tile types plus coordinates fast
create index IX0_Tile on Tile(x, y, zoom, kind);

commit;

-- write our table to a file
.backup tiles.db
