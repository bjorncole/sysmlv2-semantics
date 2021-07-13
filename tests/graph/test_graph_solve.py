from pymbe.graph.calc_lpg import CalculationGroup
from pymbe.interpretation.calc_dependencies import generate_execution_order

from pymbe.interpretation.results import *

ROCKET_BUILDING = "Model::Kerbal::Rocket Building::"
PARTS_LIBRARY = "Model::Kerbal::Parts Library::"


def test_kerbal_solve1(kerbal_lpg, kerbal_random_stage_5_complete, kerbal_stable_names):

    # check that literal assignments go correctly

    *_, qualified_name_to_id = kerbal_stable_names

    rt_10_isp_id = qualified_name_to_id[f"{PARTS_LIBRARY}RT-10 \"Hammer\" Solid Fuel Booster::Specific Impulse: "
                                        f"Real <<AttributeUsage>>"]
    ft200_full_mass = qualified_name_to_id[f'{PARTS_LIBRARY}FL-T200 Fuel Tank::Full Mass: Real <<AttributeUsage>>']

    # incrementally step through the calculations and check progress

    dcg = generate_execution_order(kerbal_lpg)

    # check first 10 literals found

    literal_output_moves = [item for item in dcg if item[2] == "Output" and 'Literal' in kerbal_lpg.nodes[item[0]]['@type']]

    print(pprint_edges(literal_output_moves, kerbal_lpg.model))

    cg1 = CalculationGroup(kerbal_lpg.get_projection("Expression Inferred"), kerbal_random_stage_5_complete, dcg)

    try:
        cg1.solve_graph(kerbal_lpg)
    except:
        pass

    for move in literal_output_moves:
        print(kerbal_random_stage_5_complete[move[1]])

    rt_10_isps = [seq[-1].value for seq in kerbal_random_stage_5_complete[rt_10_isp_id]]
    ft200_masses = [seq[-1].value for seq in kerbal_random_stage_5_complete[ft200_full_mass]]

    #assert all([full_mass == 1.125 for full_mass in ft200_masses])
    assert all(
        [isp == 170.0 for isp in rt_10_isps]
    ), f"RT-10 ISPs: {rt_10_isps}"
