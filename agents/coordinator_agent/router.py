"""
ORCA Coordinator Router.

The router analyzes a user query and determines which
specialized agents should be involved.
"""

from typing import List


class AgentRouter:
    """Routes user queries to the appropriate ORCA agents."""

    WEATHER_KEYWORDS = [
        "weather",
        "rain",
        "wind",
        "storm",
        "cyclone",
        "temperature",
        "forecast",
        "warning",
    ]

    OCEAN_KEYWORDS = [
        "wave",
        "waves",
        "current",
        "sea",
        "ocean",
        "swell",
        "tide",
    ]

    MARINE_KEYWORDS = [
        "chlorophyll",
        "fishing",
        "fish",
        "marine",
        "ecosystem",
        "plankton",
        "pfz",
        "fishing zone",
    ]

    SAFETY_KEYWORDS = [
        "safe", "safety", "danger", "risk", "dangerous",
        "alert", "warning", "cyclone", "lightning", "restricted",
        "boundary", "protected area",
    ]

    GEOSPATIAL_KEYWORDS = [
        "boundary", "geofence", "geofencing", "mpa", "protected area",
        "restricted water", "port", "distance",
    ]

    DISASTER_KEYWORDS = [
        "cyclone", "storm", "lightning", "hazard", "warning", "alert",
    ]

    SATELLITE_KEYWORDS = [
        "satellite", "imagery", "earth observation", "remote sensing",
    ]

    FISHERIES_KEYWORDS = [
        "pfz", "fishing zone", "fish", "fisheries", "fishing",
    ]

    def route(self, query: str) -> List[str]:
        """
        Determine which specialized agents are required
        for the given user query.
        """

        if not query or not query.strip():
            return []

        query_lower = query.lower()

        required_agents = set()

        # Weather-related queries
        if any(
            keyword in query_lower
            for keyword in self.WEATHER_KEYWORDS
        ):
            required_agents.add("weather_agent")

        # Ocean-related queries
        if any(
            keyword in query_lower
            for keyword in self.OCEAN_KEYWORDS
        ):
            required_agents.add("ocean_agent")

        # Marine/ecosystem-related queries
        if any(
            keyword in query_lower
            for keyword in self.MARINE_KEYWORDS
        ):
            required_agents.add("marine_agent")

        if any(keyword in query_lower for keyword in self.GEOSPATIAL_KEYWORDS):
            required_agents.add("geospatial_agent")

        if any(keyword in query_lower for keyword in self.DISASTER_KEYWORDS):
            required_agents.add("disaster_agent")

        if any(keyword in query_lower for keyword in self.SATELLITE_KEYWORDS):
            required_agents.add("satellite_agent")

        if any(keyword in query_lower for keyword in self.FISHERIES_KEYWORDS):
            required_agents.add("fisheries_agent")

        # Safety questions require information from
        # all relevant environmental agents.
        if any(
            keyword in query_lower
            for keyword in self.SAFETY_KEYWORDS
        ):
            required_agents.update(
                {
                    "weather_agent",
                    "ocean_agent",
                    "marine_agent",
                    "geospatial_agent",
                    "disaster_agent",
                }
            )

        return sorted(required_agents)


if __name__ == "__main__":
    router = AgentRouter()

    test_queries = [
        "What is the weather tomorrow?",
        "What are the wave conditions?",
        "What is the chlorophyll level?",
        "Is it safe to fish tomorrow?",
    ]

    for query in test_queries:
        agents = router.route(query)

        print(f"\nQuery: {query}")
        print(f"Agents: {agents}")
