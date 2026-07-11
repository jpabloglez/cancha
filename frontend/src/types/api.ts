// Frontend types matching the JSON shapes returned by the Django API.
// The backend exposes camelCase via djangorestframework-camel-case (spec §5.3).

export interface League {
  id: number;
  name: string;
  slug: string;
  level: number;
  country: string;
  seasonsCount: number;
  teamsCount: number;
  logo: MediaAsset | null;
}

export interface Season {
  id: number;
  league: number;
  name: string;
  startDate: string;
  endDate: string | null;
}

// A stored media asset (team logo / player photo). `url` is null when nothing
// is stored or the asset is under a takedown — render a fallback in that case.
export interface MediaAsset {
  url: string | null;
  attribution: string;
  license: string;
}

export interface Team {
  id: number;
  name: string;
  shortName: string;
  slug: string;
  city: string | null;
  foundedYear: number | null;
  officialName: string;
  arena: string;
  primaryColor: string;
  secondaryColor: string;
  website: string;
  logo: MediaAsset | null;
}

export interface AdvancedStats {
  trueShootingPercent: number;
  effectiveFieldGoalPercent: number;
  usageRate: number;
  playerEfficiencyRating: number;
}

export interface PlayerSeasonStats {
  playerId: string;
  seasonId: string;
  seasonName: string;
  gamesPlayed: number;
  minutesPerGame: number;
  pointsPerGame: number;
  reboundsPerGame: number;
  assistsPerGame: number;
  stealsPerGame: number;
  blocksPerGame: number;
  turnoversPerGame: number;
  foulsPerGame: number;
  twoPercent: number;
  threePercent: number;
  ftPercent: number;
  advanced: AdvancedStats;
}

export interface Person {
  id: number;
  firstName: string;
  lastName: string;
  slug: string;
  birthDate: string | null;
  nationality: string | null;
  displayName: string;
  birthCity: string;
  birthCountry: string;
  heightCm: number | null;
  weightKg: number | null;
  primaryPosition: string;
  dominantHand: string;
  photo: MediaAsset | null;
}

// A single club/season stint in a player's career timeline (trajectory).
export interface CareerEntry {
  seasonLabel: string;
  clubName: string;
  leagueName: string;
  teamSlug: string | null;
}

// Player detail extends Person with the full career timeline.
export interface PersonDetail extends Person {
  career: CareerEntry[];
}

export interface TeamSeason {
  id: number;
  team: Team;
  season: number;
  league: number;
}

export interface RosterStats {
  gamesPlayed: number;
  minutesPerGame: number;
  pointsPerGame: number;
  reboundsPerGame: number;
  assistsPerGame: number;
  per: number;
  tsPercent: number;
}

export interface RosterEntry {
  id: number;
  person: Person;
  jerseyNumber: number | null;
  position: string | null;
  heightCm: number | null;
  weightKg: number | null;
  stats: RosterStats | null;
}

export interface Standing {
  teamSeasonId: number;
  teamName: string;
  teamSlug: string;
  teamLogo: MediaAsset | null;
  teamPrimaryColor: string;
  gamesPlayed: number;
  wins: number;
  losses: number;
  pointsFor: number;
  pointsAgainst: number;
  pointDifference: number;
}

export interface Game {
  id: number;
  season: number;
  homeTeamSeason: number;
  awayTeamSeason: number;
  homeTeam: Team;
  awayTeam: Team;
  date: string;
  finalScoreHome: number;
  finalScoreAway: number;
  round: string | null;
}

// A team's totals within a game box score (keyed by team-season).
export interface TeamBoxScore {
  teamSeason: number;
  points: number;
  reboundsOff: number;
  reboundsDef: number;
  assists: number;
  steals: number;
  blocks: number;
  turnovers: number;
  fouls: number;
  fieldGoalsMade: number;
  fieldGoalsAtt: number;
  threePointMade: number;
  threePointAtt: number;
  freeThrowsMade: number;
  freeThrowsAtt: number;
}

// One player's line within a game box score.
export interface PlayerBoxScore extends TeamBoxScore {
  person: Person;
  minutesPlayed: number;
}

export interface BoxScore {
  game: Game;
  teamStats: TeamBoxScore[];
  playerStats: PlayerBoxScore[];
}

export interface AllTimeLeader {
  playerId: number;
  playerName: string;
  playerSlug: string;
  photo: MediaAsset | null;
  nationality: string | null;
  primaryPosition: string | null;
  totalGames: number;
  seasonsCount: number;
  leagues: string[];
  totalPoints: number;
  totalRebounds: number;
  totalAssists: number;
  ppg: number;
  rpg: number;
  apg: number;
  spg: number;
  bpg: number;
  topg: number;
  twoPercent: number;
  threePercent: number;
  ftPercent: number;
  per: number | null;
  tsPercent: number;
  statValue: number;
}

export interface AllTimeLeaderPage {
  count: number;
  results: AllTimeLeader[];
}

export interface PlayerOfTheDay {
  player: PersonDetail;
  latestStats: PlayerSeasonStats | null;
}

// Team statistics blocks returned by /teams/{slug}/season-stats/.
export interface TeamStatsBlock {
  points: number;
  twoMade: number;
  threeMade: number;
  ftMade: number;
  rebOff: number;
  rebDef: number;
  rebounds: number;
  assists: number;
  turnovers: number;
  steals: number;
  blocks: number;
  fouls: number;
}

export interface TeamAdvancedStats {
  ortg: number;
  drtg: number;
  pace: number;
  tsPercent: number;
  efgPercent: number;
  threeRate: number;
  ftRate: number;
  tovPercent: number;
  rebOffPct: number;
  rebDefPct: number;
  stealPct: number;
  blockPct: number;
}

export interface TeamSeasonStatsEntry {
  gamesPlayed: number;
  perGame: TeamStatsBlock;
  per100: TeamStatsBlock;
  advanced: TeamAdvancedStats;
}

export interface TeamSeasonStats {
  team: TeamSeasonStatsEntry;
  leagueAvg: TeamSeasonStatsEntry;
}

export interface TeamStatsHistoryEntry {
  season: { id: number; name: string; startDate: string };
  team: TeamSeasonStatsEntry;
  leagueAvg: TeamSeasonStatsEntry;
}

export interface Leader {
  playerId: number;
  playerName: string;
  playerSlug: string;
  seasonId: number;
  stat: string;
  value: number;
  photo: MediaAsset | null;
  team: Team | null;
}

export interface LeagueFreshness {
  slug: string;
  name: string;
  lastGameDate: string | null;
}

export interface DataFreshness {
  lastUpdated: string | null;
  byLeague: LeagueFreshness[];
}

// DRF LimitOffsetPagination envelope.
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
