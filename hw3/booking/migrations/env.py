from booking.models import Base
from common.migrations import run

run(Base.metadata)
