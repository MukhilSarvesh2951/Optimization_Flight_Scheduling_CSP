# Crew Scheduling - Operations Research Project - Date

## Disclaimer 
The data is intended for use only within the scope of the Operations Research Practice Project in Winter semester of 2025/2026 and should not be shared outside of the project Operations Research Practical Project at RWTH Aachen University.
Any use of the data outside of this project needs a written perimission from Lufthansa Industry Solutions AS GmbH. The contact persons:
- Bartlomiej Jezierski <bartlomiej.jezierski@lhind.dlh.de>
- Joseph Doetsch <joseph.doetsch@lhind.dlh.de>


## Data description
### codes.csv
- “Off Requests” (codes that start with O_) are requests from captains – they are not entitled to approval, but these days should be granted at a high approval rate, they can all be treated the same. 
- Cure / medical rehabilitation, vacation days and special leaves can all be treated as days when captains are not available

## flight_schedule.csv:
- All the flights that need to be assigned to captains
- The times are provided in CET (relevant for `fdt_limits.csv`)

## ground_transportation_times.csv
- Calculated average ground transportation times between different pairs of cities 

## home_bases.csv
- Contains all available captains together with their home base

## off_claims_2025xx.csv
- Number of so called off claims - days each captain is expected to be off for each month. All granted "off requests" and additional days off count to the number of off claims. The days on which a captain is anavailable due to the codes KUR, U, SU do not count to off claims. 
- The divergence between the number of off claims and actual days assigned as off to each captain should be minimized

## off_requests_2025xx.csv
- Specific "off requests", refer to the `codes.csv` section
- The times here are all provided in UTC

## standby.csv:
- The total number of reserve shifts expected for each month for each base
- Each reserve shift has a duration of 12 hours
- There are two types of shifts: early that starts between 0200 und 0600 local time und late that starts between 1200 und 1600
- The shifts are distributed between early and late ones as well as between individual days of a month to reflect the distribution of flights from the base

## fdt_limits.csv:
- The maximum allowed duration of a duty in hours (duty time) based on what the activation time for a captain is and the number of legs in a duty. Refer to the project overview PDF for more details regarding what is considered a duty time.



