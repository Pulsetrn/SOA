from common.migrations import run
from flight.models import Base

run(Base.metadata)
