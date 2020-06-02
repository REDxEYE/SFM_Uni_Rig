import traceback

try:


    import sfm
except:
    from sfm import sfmUtils
import sys,os.path,vs
from random import *


# ==================================================================================================
def ParentMaintainWorldSafe(child, parent):
    if child is not None and parent is not None:
        sfmUtils.ParentMaintainWorld(child, parent)
    else:
        print_("Err in ParentSafe {} - {}".format(child.name,parent.name))

# ==================================================================================================
def AddDagControlsToGroupSafe(group, *dagList):
    for dag in dagList:
        if (dag != None):
            sfmUtils.AddDagControlsToGroup(group, dag)


# ==================================================================================================
# This return a List of DAGs by their names if there are any.
def GetDAGsByNames(DAGNames):
    DAGList = []
    if (DAGNames != None):
        for name in DAGNames:
            candidate = sfm.FindDag(name)
            if (candidate != None):
                DAGList.append(candidate)
                print 'Found special DAG: ' + name
            else:
                print 'Not found special DAG: ' + name + '. This is not an error.'
    return DAGList


# ==================================================================================================
def AddValidObjectToList(objectList, obj):
    if (obj != None): objectList.append(obj)


# ==================================================================================================
def HideControlGroups(rig, rootGroup, *groupNames):
    for name in groupNames:
        group = rootGroup.FindChildByName(name, False)
        if (group != None):
            try:
                rig.HideControlGroup(group)
            except:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                TB = traceback.format_tb(exc_traceback)
                sfm.Msg("Err: {}\n {}\n {} \n".format(exc_type, exc_value, ''.join(TB)))


# ==================================================================================================
# Create the reverse foot control and operators for the foot on the specified side
# ==================================================================================================
def CreateReverseFoot(controlName, sideName, gameModel, animSet, shot, helperControlGroup, footControlGroup,
                      BipedBallOverride=False):
    # Cannot create foot controls without heel position, so check for that first
    heelAttachName = "pvt_heel_" + sideName
    if (gameModel.FindAttachment(heelAttachName) == 0):
        print "Could not create foot control " + controlName + ", model is missing heel attachment point: " + heelAttachName;
        return None

    footRollDefault = 0.5
    rotationAxisX = vs.Vector(1, 0, 0)
    rotationAxisY = vs.Vector(0, 1, 0)
    rotationAxisZ = vs.Vector(0, 0, 1)

    # Construct the name of the dag nodes of the foot and toe for the specified side
    footName = "rig_foot_" + sideName
    toeName = "rig_toe_" + sideName

    # Get the world space position and orientation of the foot and toe
    footPos = sfm.GetPosition(footName)
    footRot = sfm.GetRotation(footName)
    toePos = sfm.GetPosition(toeName)

    # Setup the reverse foot hierarchy such that the foot is the parent of all the foot transforms, the
    # reverse heel is the parent of the heel, so it can be used for rotations around the ball of the
    # foot that will move the heel, the heel is the parent of the foot IK handle so that it can perform
    # rotations around the heel and move the foot IK handle, resulting in moving all the foot bones.
    # root
    #   + rig_foot_R
    #       + rig_knee_R
    #       + rig_reverseHeel_R
    #           + rig_heel_R
    #               + rig_footIK_R


    # Construct the reverse heel joint this will be used to rotate the heel around the toe, and as
    # such is positioned at the toe, but using the rotation of the foot which will be its parent,
    # so that it has no local rotation once parented to the foot.
    reverseHeelName = "rig_reverseHeel_" + sideName
    reverseHeelDag = sfm.CreateRigHandle(reverseHeelName, pos=toePos, rot=footRot, rotControl=False)
    sfmUtils.Parent(reverseHeelName, footName, vs.REPARENT_LOGS_OVERWRITE)

    # Construct the heel joint, this will be used to rotate the foot around the back of the heel so it
    # is created at the heel location (offset from the foot) and also given the rotation of its parent.
    heelName = "rig_heel_" + sideName
    vecHeelPos = gameModel.ComputeAttachmentPosition(heelAttachName)
    heelPos = [vecHeelPos.x, vecHeelPos.y, vecHeelPos.z]
    heelRot = sfm.GetRotation(reverseHeelName)
    heelDag = sfm.CreateRigHandle(heelName, pos=heelPos, rot=heelRot, posControl=True, rotControl=False)
    sfmUtils.Parent(heelName, reverseHeelName, vs.REPARENT_LOGS_OVERWRITE)

    # Create the ik handle which will be used as the target for the ik chain for the leg
    ikHandleName = "rig_footIK_" + sideName
    ikHandleDag = sfmUtils.CreateHandleAt(ikHandleName, footName)
    sfmUtils.Parent(ikHandleName, heelName, vs.REPARENT_LOGS_OVERWRITE)

    # Create an orient constraint which causes the toe"s orientation to match the foot"s orientation
    footRollControlName = controlName + "_" + sideName
    toeOrientTarget = sfm.OrientConstraint(footName, toeName, mo=True, controls=False)
    footRollControl, footRollValue = sfmUtils.CreateControlledValue(footRollControlName, "value", vs.AT_FLOAT,
                                                                    footRollDefault, animSet, shot)

    # Create the expressions to re-map the footroll slider value for use in the constraint and rotation operators
    toeOrientExprName = "expr_toeOrientEnable_" + sideName
    toeOrientExpr = sfmUtils.CreateExpression(toeOrientExprName, "inrange( footRoll, 0.5001, 1.0 )", animSet)
    toeOrientExpr.SetValue("footRoll", footRollDefault)

    toeRotateExprName = "expr_toeRotation_" + sideName
    toeRotateExpr = sfmUtils.CreateExpression(toeRotateExprName, "max( 0, (footRoll - 0.5) ) * 140", animSet)
    toeRotateExpr.SetValue("footRoll", footRollDefault)

    heelRotateExprName = "expr_heelRotation_" + sideName
    heelRotateExpr = sfmUtils.CreateExpression(heelRotateExprName, "max( 0, (0.5 - footRoll) ) * -100", animSet)
    heelRotateExpr.SetValue("footRoll", footRollDefault)

    # Create a connection from the footroll value to all of the expressions that require it
    footRollConnName = "conn_footRoll_" + sideName
    footRollConn = sfmUtils.CreateConnection(footRollConnName, footRollValue, "value", animSet)
    footRollConn.AddOutput(toeOrientExpr, "footRoll")
    footRollConn.AddOutput(toeRotateExpr, "footRoll")
    footRollConn.AddOutput(heelRotateExpr, "footRoll")

    # Create the connection from the toe orientation enable expression to the target weight of the
    # toe orientation constraint, this will turn the constraint on an off based on the footRoll value
    toeOrientConnName = "conn_toeOrientExpr_" + sideName;
    toeOrientConn = sfmUtils.CreateConnection(toeOrientConnName, toeOrientExpr, "result", animSet)
    toeOrientConn.AddOutput(toeOrientTarget, "targetWeight")

    # Create a rotation constraint to drive the toe rotation and connect its input to the
    # toe rotation expression and connect its output to the reverse heel dag"s orientation
    toeRotateConstraintName = "rotationConstraint_toe_" + sideName
    toeRotateConstraint = sfmUtils.CreateRotationConstraint(toeRotateConstraintName, rotationAxisX, reverseHeelDag,
                                                            animSet)

    toeRotateExprConnName = "conn_toeRotateExpr_" + sideName
    toeRotateExprConn = sfmUtils.CreateConnection(toeRotateExprConnName, toeRotateExpr, "result", animSet)
    toeRotateExprConn.AddOutput(toeRotateConstraint, "rotations", 0);

    # Create a rotation constraint to drive the heel rotation and connect its input to the
    # heel rotation expression and connect its output to the heel dag"s orientation
    heelRotateConstraintName = "rotationConstraint_heel_" + sideName
    heelRotateConstraint = sfmUtils.CreateRotationConstraint(heelRotateConstraintName, rotationAxisX, heelDag, animSet)

    heelRotateExprConnName = "conn_heelRotateExpr_" + sideName
    heelRotateExprConn = sfmUtils.CreateConnection(heelRotateExprConnName, heelRotateExpr, "result", animSet)
    heelRotateExprConn.AddOutput(heelRotateConstraint, "rotations", 0)

    ######################################################################################







    if (helperControlGroup != None):
        sfmUtils.AddDagControlsToGroup(helperControlGroup, reverseHeelDag, ikHandleDag, heelDag)

    if (footControlGroup != None):
        footControlGroup.AddControl(footRollControl)

    return ikHandleDag


# ==================================================================================================
# Compute the direction from boneA to boneB
# ==================================================================================================
def ComputeVectorBetweenBones(boneA, boneB, scaleFactor):
    vPosA = vs.Vector(0, 0, 0)
    boneA.GetAbsPosition(vPosA)

    vPosB = vs.Vector(0, 0, 0)
    boneB.GetAbsPosition(vPosB)

    vDir = vs.Vector(0, 0, 0)
    vs.mathlib.VectorSubtract(vPosB, vPosA, vDir)
    vDir.NormalizeInPlace()

    vScaledDir = vs.Vector(0, 0, 0)
    vs.mathlib.VectorScale(vDir, scaleFactor, vScaledDir)

    return vScaledDir

def getpath():
    return os.path.dirname(os.path.abspath("bip_universalV4.py"))
# ==================================================================================================
# Build a simple ik rig for the currently selected animation set
# ==================================================================================================
DEBUG = open(os.path.join(getpath(),"UniV4Out.txt"),"w")

def print_(s):
    sfm.Msg(str(s))
    sfm.Msg('\n')
    DEBUG.write(str(s)+"\n")
print_(os.path.join(getpath(),"UniV4Out.txt"))
def FindAllBones():
    count = 0
    bonelist = []
    tmpDag = "null"
    while (tmpDag != None):
        tmpDag = sfm.NextSelectedDag()
        bonelist.append(tmpDag)
    return bonelist


def ClearName(name):
    if "(" in str(name):

        b = str(name).find('(')
        e = str(name).find(')')
        bonename = str(name)[b + 1:e]
    else:
        bonename = str(name)
    return bonename


def BuildRig():
    # Get the currently selected animation set and shot
    shot = sfm.GetCurrentShot()
    animSet = sfm.GetCurrentAnimationSet()
    gameModel = animSet.gameModel
    rootGroup = animSet.GetRootControlGroup()

    # Start the biped rig to which all of the controls and constraints will be added

    rig = sfm.BeginRig("rig_Universal_" + animSet.GetName() + str(randint(0, 128)))
    HideControlGroups(rig, rootGroup, "Body", "Arms", "Legs", "Root")
    if (rig == None):
        return
    # sfm.Msg('dir')
    # sfm.Msg(str(dir(rig)))
    # Change the operation mode to passthrough so changes chan be made temporarily
    sfm.SetOperationMode("Pass")

    # Move everything into the reference pose

    sfm.SelectAll()
    sfm.SetReferencePose()
    allbones = FindAllBones()
    print_(dir(allbones[0]))
    bones = {}
    boneRoot = sfmUtils.FindFirstDag(["RootTransform"])
    #Root = sfmUtils.CreateConstrainedHandle("rig_root", boneRoot, bCreateControls=False)
    for bone in allbones:

        try:

            if "_GameModel" in str(bone.name):
                print_("RootTransform bone")
                continue
            if "_GameModel" in str(bone.GetParent().name):
                tempbone = boneRoot
            else:
                tempbone = sfmUtils.FindFirstDag([ClearName(bone.GetParent().name)])
            if "viewTarget" in str(bone.name):
                print_("Skiping ViewTarget bone")
                continue
            print_("Parent for {} : {}".format(ClearName(bone.name), ClearName(tempbone.name)))
            bone = sfmUtils.FindFirstDag([ClearName(bone.name)])
            temprig = sfmUtils.CreateConstrainedHandle("rig_{}".format(ClearName(bone.name)), bone,bCreateControls=False)
            bones[ClearName(bone.name)] = [bone, tempbone, ClearName(tempbone.name), temprig]
        except:
            print_("Bone {} has no parent :(".format(bone))
    print_(bones)
    sfm.ClearSelection()
    sfmUtils.SelectDagList(list([bones[bone][3] for bone in bones]))

    sfm.GenerateSamples()
    sfm.RemoveConstraints()
    for bone in bones:

        Tempbone = bones[bone]
        if "viewTarget" in str(Tempbone[0].name):
            continue
        if "_GameModel" in Tempbone[2]:
            print_("Parenting {} to {} ({}) with possible error".format(bone, "RootTransform",Tempbone[2]))

            ParentMaintainWorldSafe(Tempbone[3], boneRoot)
        else:
            print_("Parenting {} to {}".format(bone, Tempbone[2]))
            ParentMaintainWorldSafe(Tempbone[3], bones[Tempbone[2]][3])
    #sfmUtils.CreatePointOrientConstraint(Root, boneRoot)
    for bone in bones:

        Tempbone = bones[bone]
        print_("Constraining {} to {}".format(ClearName(Tempbone[0].name),ClearName(Tempbone[3].name)))
        sfmUtils.CreatePointOrientConstraint(Tempbone[0], Tempbone[3])

    # End the rig definition
    sfm.EndRig()

    print 'Rig was built successfully.'
    return


# ==================================================================================================
# Script entry
# ==================================================================================================

# Construct the rig for the selected animation set
BuildRig();
DEBUG.close()